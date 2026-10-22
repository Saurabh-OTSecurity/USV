import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class IngestionTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    token_id: uuid.UUID
    site_id: uuid.UUID
    status: str
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class IngestionTokenIssuedResponse(IngestionTokenResponse):
    # Shown exactly once, at issuance. Format: "<token_id>.<secret>" -- point
    # the new site's Tribot usv_push config at this ECC's
    # POST /api/v1/ingest/tribot with this value as its bearer credential.
    token: str


class EventEnvelope(BaseModel):
    """The wire contract event envelope (TRIBOT_ECC_INTEGRATION_SPEC.md
    Section 5.2 / ECC_USV_PLATFORM_SPEC.md Section 8). `siteId` in the
    envelope is accepted for Tribot-side traceability/logging only -- FR-2.2
    is explicit that the *authoritative* site_id/tenant_id always come from
    the ingestion credential, never the request body, so a forged siteId in
    the payload can never make one site's push land in another site's data.
    """

    eventId: str
    eventType: str
    siteId: str | None = None
    objectType: str
    objectId: str | None = None
    occurredAt: datetime
    payload: dict[str, Any]


class IngestAcceptedResponse(BaseModel):
    status: str  # "accepted" | "duplicate"
    eventId: str


# Per-request cap for the batch receiver: big enough that a site's full
# resync (a few hundred assets plus alerts) is a handful of requests, small
# enough that one request's insert stays well under a second.
MAX_BATCH_EVENTS = 500


class EventBatch(BaseModel):
    """Body of POST /api/v1/ingest/tribot/batch. Events are taken as raw
    dicts and validated one by one (see ingest.py), so one malformed event is
    reported as rejected instead of failing the other events in the batch."""

    events: list[dict[str, Any]]
    # Tribot self-health sent with every heartbeat (USV O&M Manual section 7):
    # captureRunning, lastPacketAt, diskFreePercent, version, tribotTime, ...
    health: dict[str, Any] | None = None


class BatchEventResult(BaseModel):
    eventId: str | None
    status: str  # "accepted" | "duplicate" | "rejected"
    error: str | None = None


class BatchIngestResponse(BaseModel):
    accepted: int
    duplicate: int
    rejected: int
    results: list[BatchEventResult]
