from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.tenancy import session_for_ingestion_token
from app.models.monitoring import IngestionAuthFailure
from app.schemas.ingestion import (
    MAX_BATCH_EVENTS, BatchEventResult, BatchIngestResponse, EventBatch, EventEnvelope, IngestAcceptedResponse,
)
from app.services.ingestion_service import receive_event, receive_events, record_site_health
from app.services.ingestion_token_service import IngestionTokenService, InvalidIngestionCredentialError

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

# Deliberately separate from app.core.rbac's bearer scheme/get_current_user:
# this endpoint authenticates a *machine* (a Tribot instance's usv_push
# credential, FR-1.4), never a human UsvUser session, so it is never
# reachable via a UsvUser JWT and a UsvUser JWT is never accepted here.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_ingest_db(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)):
    """The database holding this ingestion token: the one database in
    SINGLE_TENANT mode; the token's customer database in pool mode."""
    db = session_for_ingestion_token(credentials.credentials if credentials else None)
    try:
        yield db
    finally:
        db.close()


def _record_refusal(db: Session, request: Request, error: InvalidIngestionCredentialError) -> None:
    """Every refused ingest request is kept for the rejected-connections
    alert (SU-08, USV O&M Manual section 7)."""
    db.rollback()
    db.add(IngestionAuthFailure(reason=error.reason, token_id=error.token_id, site_id=error.site_id,
                                source_ip=request.client.host if request.client else None))
    db.commit()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid or missing ingestion credential"}},
    )


@router.post("/tribot", response_model=IngestAcceptedResponse, status_code=202)
def ingest_tribot_event(
    envelope: EventEnvelope,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_ingest_db),
) -> IngestAcceptedResponse:
    """Receiver for a Tribot instance's `usv_push` deliveries (FR-2.1,
    ECC_USV_PLATFORM_SPEC.md Decision 1/Task T-2). This repo's primary
    ingestion path -- the legacy live pull-proxy under /api/v1/tribot/* is
    NOT superseded by this and stays as an on-demand single-site drill-down.

    Returns fast (202) after writing to the ingested_event staging table;
    normalization into fleet_asset/alert/finding/remediation/incident
    happens asynchronously (app/services/ingestion_worker.py) so a slow or
    erroring receiver never backpressures the Tribot instance sending it
    (NFR, Section 9 of both specs).
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized()

    try:
        token = IngestionTokenService(db).authenticate(credentials.credentials)
    except InvalidIngestionCredentialError as error:
        _record_refusal(db, request, error)
        raise _unauthorized()

    status = receive_event(db, token, envelope)
    return IngestAcceptedResponse(status=status, eventId=envelope.eventId)


@router.post("/tribot/batch", response_model=BatchIngestResponse, status_code=202)
def ingest_tribot_events(
    batch: EventBatch,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_ingest_db),
) -> BatchIngestResponse:
    """Batch receiver for many-site deployments: up to MAX_BATCH_EVENTS
    envelopes per request, one credential check and one staging INSERT per
    request instead of per event. Same contract as the single-event route
    (same envelope, same idempotency on eventId, site/tenant from the
    credential only). Each event is validated separately and reported in
    `results` in request order, so a malformed event is "rejected" without
    failing the rest of the batch."""
    if credentials is None or not credentials.credentials:
        raise _unauthorized()
    try:
        token = IngestionTokenService(db).authenticate(credentials.credentials)
    except InvalidIngestionCredentialError as error:
        _record_refusal(db, request, error)
        raise _unauthorized()

    if batch.health is not None:
        record_site_health(db, token, batch.health)

    if len(batch.events) > MAX_BATCH_EVENTS:
        raise HTTPException(
            status_code=413,
            detail={"error": {"code": "BATCH_TOO_LARGE", "message": f"At most {MAX_BATCH_EVENTS} events per request"}},
        )

    valid: list[EventEnvelope] = []
    results: list[BatchEventResult | EventEnvelope] = []
    for raw in batch.events:
        try:
            envelope = EventEnvelope.model_validate(raw)
        except ValidationError as exc:
            event_id = raw.get("eventId") if isinstance(raw, dict) else None
            results.append(BatchEventResult(eventId=event_id if isinstance(event_id, str) else None,
                                            status="rejected", error=str(exc.errors()[0]["msg"])[:200]))
            continue
        valid.append(envelope)
        results.append(envelope)

    statuses = receive_events(db, token, valid)
    final = [
        BatchEventResult(eventId=r.eventId, status=statuses[r.eventId]) if isinstance(r, EventEnvelope) else r
        for r in results
    ]
    counts = {s: sum(1 for r in final if r.status == s) for s in ("accepted", "duplicate", "rejected")}
    return BatchIngestResponse(**counts, results=final)
