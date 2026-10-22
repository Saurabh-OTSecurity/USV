import uuid
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit
from app.models.fleet_lifecycle import SiteHealth
from app.models.ingested_event import IngestedEvent
from app.models.ingestion_token import IngestionToken
from app.models.site import Site
from app.schemas.ingestion import EventEnvelope


def resolve_tenant_id_for_site(db: Session, site_id: uuid.UUID) -> uuid.UUID:
    site = db.get(Site, site_id)
    business_unit = db.get(BusinessUnit, site.business_unit_id)
    return business_unit.tenant_id


def receive_event(db: Session, token: IngestionToken, envelope: EventEnvelope) -> str:
    """Writes the envelope to the ingested_event staging table synchronously
    and fast -- no normalization happens on this path (T-2's async-receive
    requirement). Idempotent on eventId via ON CONFLICT DO NOTHING: a
    retried delivery of an event already seen is a no-op, never reprocessed
    (FRD Section 35). Returns "accepted" or "duplicate".

    site_id/tenant_id come from the authenticated `token`, never from the
    envelope body (FR-2.2) -- envelope.siteId, if present, is not trusted
    for anything beyond Tribot-side log correlation.
    """
    tenant_id = resolve_tenant_id_for_site(db, token.site_id)

    stmt = (
        pg_insert(IngestedEvent)
        .values(
            event_id=envelope.eventId,
            tenant_id=tenant_id,
            site_id=token.site_id,
            token_id=token.token_id,
            event_type=envelope.eventType,
            object_type=envelope.objectType,
            object_id=envelope.objectId,
            occurred_at=envelope.occurredAt,
            raw_payload=envelope.model_dump(mode="json"),
            process_status="pending",
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(IngestedEvent.event_id)
    )
    result = db.execute(stmt)
    db.commit()
    return "accepted" if result.first() is not None else "duplicate"


def record_site_health(db: Session, token: IngestionToken, health: dict) -> None:
    """Keeps the latest heartbeat health per site (one row, overwritten), and
    the clock skew between this USV and the Tribot's own clock (health
    "tribotTime"), for the site clock-skew alert."""
    now = datetime.now(timezone.utc)
    skew = None
    try:
        tribot_time = datetime.fromisoformat(str(health.get("tribotTime", "")).replace("Z", "+00:00"))
        if tribot_time.tzinfo is None:
            tribot_time = tribot_time.replace(tzinfo=timezone.utc)
        skew = (now - tribot_time).total_seconds()
    except ValueError:
        pass
    stmt = pg_insert(SiteHealth).values(
        site_id=token.site_id, tenant_id=resolve_tenant_id_for_site(db, token.site_id),
        health=health, received_at=now, clock_skew_seconds=skew,
    )
    db.execute(stmt.on_conflict_do_update(
        index_elements=["site_id"],
        set_={"health": stmt.excluded.health, "received_at": stmt.excluded.received_at,
              "clock_skew_seconds": stmt.excluded.clock_skew_seconds},
    ))
    db.commit()


def receive_events(db: Session, token: IngestionToken, envelopes: list[EventEnvelope]) -> dict[str, str]:
    """Batch form of receive_event(): one multi-row INSERT ... ON CONFLICT DO
    NOTHING for the whole batch, same idempotency and same token-derived
    site/tenant attribution. Returns {eventId: "accepted" | "duplicate"}; an
    eventId repeated inside the batch counts once."""
    if not envelopes:
        return {}
    tenant_id = resolve_tenant_id_for_site(db, token.site_id)

    unique: dict[str, EventEnvelope] = {}
    for envelope in envelopes:
        unique.setdefault(envelope.eventId, envelope)

    stmt = (
        pg_insert(IngestedEvent)
        .values([
            {
                "event_id": envelope.eventId,
                "tenant_id": tenant_id,
                "site_id": token.site_id,
                "token_id": token.token_id,
                "event_type": envelope.eventType,
                "object_type": envelope.objectType,
                "object_id": envelope.objectId,
                "occurred_at": envelope.occurredAt,
                "raw_payload": envelope.model_dump(mode="json"),
                "process_status": "pending",
            }
            for envelope in unique.values()
        ])
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(IngestedEvent.event_id)
    )
    inserted = {row[0] for row in db.execute(stmt)}
    db.commit()
    return {event_id: "accepted" if event_id in inserted else "duplicate" for event_id in unique}
