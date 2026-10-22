"""Normalizes staged app.models.ingested_event.IngestedEvent rows into the
fleet_* tables. This is the receiving-side mirror of the durable outbox
TRIBOT_ECC_INTEGRATION_SPEC.md's T-3 builds on the sending side: the HTTP
receiver (app/api/routes/ingest.py) only ever writes to `ingested_event` and
returns; this module does the actual normalization work, run either by the
background loop started in app/main.py's lifespan, or synchronously by
tests/scripts that want deterministic processing.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text, tuple_
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.fleet_asset import FleetAsset
from app.models.fleet_lifecycle import FleetAssetTombstone, FleetObject, FleetTopologyLink
from app.models.incident import Incident
from app.models.ingested_event import IngestedEvent
from app.models.remediation import Remediation
from app.services.correlation_service import correlate_alert

logger = logging.getLogger("app.ingestion_worker")

# NOTE: `finding` is intentionally excluded from this pass's normalization --
# TRIBOT_ECC_INTEGRATION_SPEC.md's Task T-2 (Tribot side) hasn't shipped the
# Finding entity yet, so its wire shape isn't final. The finding_id lookup
# below would otherwise upsert against field names Tribot's own spec says
# are still subject to change; safer to hold events of this object_type as
# pending than guess a shape and have to re-migrate later.
_HANDLED_OBJECT_TYPES = {"asset", "alert", "remediation", "incident", "ir_case", "topology_link", "site_inventory",
                         "vulnerability", "software", "patch", "site_config"}

# Detail records kept raw in fleet_object for the Tribot-style site views:
# object type -> the payload key holding Tribot's own id for it.
_OBJECT_ID_KEYS = {
    "vulnerability": "vulnerabilityId",
    "software": "softwareId",
    "patch": "patchId",
    "ir_case": "caseId",
    "site_config": "configId",
}

# Statuses (Tribot's vocabulary) that mean an alert is no longer open.
CLOSED_ALERT_STATUSES = ("Closed", "Resolved", "Suppressed", "False Positive")


class EventIgnored(Exception):
    """Raised by a normalizer for an event that is valid but must not be
    applied (e.g. an asset event older than the asset's decommission). The
    event is marked 'skipped' with this reason, not 'failed'."""


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _first_present(payload: dict, *keys: str):
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


# Per-batch lookup cache (see process_pending_events): {(model, site_id,
# source_id): row or None}. Lives in Session.info so it is scoped to the one
# session processing the batch.
_CACHE_KEY = "fleet_row_cache"

# (model, its source-id column, payload keys holding that id) per object type
_LOOKUP = {
    "asset": (FleetAsset, "source_asset_id", ("asset_id", "assetId")),
    "alert": (Alert, "source_alert_id", ("alert_id", "alertId")),
    "incident": (Incident, "source_incident_id", ("incident_id", "incidentId")),
    "ir_case": (Incident, "source_incident_id", ("incident_id", "incidentId")),
    "remediation": (Remediation, "source_remediation_id", ("remediation_id", "remediationId")),
    "topology_link": (FleetTopologyLink, "source_link_id", ("linkId",)),
}


def _store_object(db: Session, event: IngestedEvent, object_type: str, payload: dict) -> None:
    """Upserts one raw detail record (fleet_object). Not cached: each id is
    rare enough in a batch that a direct upsert is simplest."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    source_id = payload.get(_OBJECT_ID_KEYS[object_type]) or event.object_id
    if not source_id:
        raise ValueError(f"{object_type} event missing {_OBJECT_ID_KEYS[object_type]}")
    stmt = pg_insert(FleetObject).values(
        tenant_id=event.tenant_id, site_id=event.site_id, object_type=object_type, source_id=str(source_id),
        asset_source_id=str(payload["assetId"]) if payload.get("assetId") else None, raw=payload,
    )
    db.execute(stmt.on_conflict_do_update(
        index_elements=["site_id", "object_type", "source_id"],
        set_={"raw": stmt.excluded.raw, "asset_source_id": stmt.excluded.asset_source_id, "updated_at": func.now()},
    ))


def _normalize_object(db: Session, event: IngestedEvent) -> None:
    _store_object(db, event, event.object_type, event.raw_payload.get("payload", {}))


def _find_existing(db: Session, model, source_column: str, site_id, source_id: str):
    cache = db.info.get(_CACHE_KEY)
    key = (model, site_id, source_id)
    if cache is not None and key in cache:
        return cache[key]
    return db.execute(
        select(model).where(model.site_id == site_id, getattr(model, source_column) == source_id)
    ).scalar_one_or_none()


def _remember(db: Session, model, site_id, source_id: str, row) -> None:
    cache = db.info.get(_CACHE_KEY)
    if cache is not None:
        cache[(model, site_id, source_id)] = row


def _prefetch(db: Session, events) -> None:
    """Loads every fleet row the batch will touch with one query per model,
    instead of one SELECT per event."""
    cache = db.info[_CACHE_KEY]
    wanted: dict = {}
    for event in events:
        lookup = _LOOKUP.get(event.object_type)
        if lookup is None:
            continue
        model, column, keys = lookup
        payload = event.raw_payload.get("payload", {})
        source_id = _first_present(payload, *keys) or event.object_id
        if source_id:
            wanted.setdefault((model, column), set()).add((event.site_id, str(source_id)))
        if event.object_type == "asset" and source_id:
            wanted.setdefault((FleetAssetTombstone, "source_asset_id"), set()).add((event.site_id, str(source_id)))
        if event.object_type == "alert" and payload.get("assetId"):
            # alerts are linked to their fleet asset (alert.asset_id)
            wanted.setdefault((FleetAsset, "source_asset_id"), set()).add((event.site_id, str(payload["assetId"])))
    for (model, column), pairs in wanted.items():
        for key in pairs:
            cache[(model,) + key] = None
        pairs = list(pairs)
        for start in range(0, len(pairs), 1000):
            rows = db.execute(
                select(model).where(tuple_(model.site_id, getattr(model, column)).in_(pairs[start:start + 1000]))
            ).scalars()
            for row in rows:
                cache[(model, row.site_id, getattr(row, column))] = row


def _normalize_asset(db: Session, event: IngestedEvent) -> None:
    """Asset events: ASSET_DECOMMISSIONED and ASSET_RESTORED act on the
    lifecycle (manual section 6); anything else is an upsert, ignored if it
    happened at or before the asset's decommission (tombstone)."""
    payload = event.raw_payload.get("payload", {})
    source_asset_id = _first_present(payload, "asset_id", "assetId") or event.object_id
    if not source_asset_id:
        raise ValueError("asset event missing asset_id")
    source_asset_id = str(source_asset_id)

    if event.event_type == "ASSET_DECOMMISSIONED":
        decommission_fleet_asset(
            db, event.tenant_id, event.site_id, source_asset_id,
            reason=payload.get("reason") or "decommissioned in Tribot",
            decommissioned_by=payload.get("decommissionedBy"),
            decommissioned_at=_parse_time(payload.get("decommissionedAt")) or event.occurred_at,
            asset_name=payload.get("name"), origin="tribot",
        )
        return
    if event.event_type == "ASSET_RESTORED":
        tombstone = _find_existing(db, FleetAssetTombstone, "source_asset_id", event.site_id, source_asset_id)
        if tombstone is not None and tombstone.restored_at is None:
            tombstone.restored_at = event.occurred_at
            db.add(AuditLog(occurred_at=datetime.now(timezone.utc), event_type="fleet_asset_restored",
                            result="success", target_type="fleet_asset",
                            detail={"site_id": str(event.site_id), "source_asset_id": source_asset_id,
                                    "restored_by": payload.get("restoredBy")}))
        if isinstance(payload.get("asset"), dict):
            _upsert_asset(db, event, source_asset_id, payload["asset"])
        return

    tombstone = _find_existing(db, FleetAssetTombstone, "source_asset_id", event.site_id, source_asset_id)
    if tombstone is not None and tombstone.restored_at is None and event.occurred_at <= tombstone.decommissioned_at:
        raise EventIgnored(f"asset {source_asset_id} was decommissioned at {tombstone.decommissioned_at.isoformat()}")
    _upsert_asset(db, event, source_asset_id, payload)


def _upsert_asset(db: Session, event: IngestedEvent, source_asset_id: str, payload: dict) -> None:
    existing = _find_existing(db, FleetAsset, "source_asset_id", event.site_id, source_asset_id)

    now = datetime.now(timezone.utc)
    if existing is None:
        existing = FleetAsset(
            # id assigned here, not by the database, so an alert for this
            # asset later in the same batch can link to it before the flush
            asset_id=uuid.uuid4(),
            tenant_id=event.tenant_id,
            site_id=event.site_id,
            source_asset_id=source_asset_id,
            first_seen_at=now,
        )
        db.add(existing)
        _remember(db, FleetAsset, event.site_id, source_asset_id, existing)

    existing.name = _first_present(payload, "name") or existing.name
    existing.device_type = _first_present(payload, "device_type", "deviceType") or existing.device_type
    existing.risk_level = _first_present(payload, "risk_level", "riskLevel") or existing.risk_level
    existing.industrial_zone = _first_present(payload, "industrial_zone", "industrialZone") or existing.industrial_zone
    existing.purdue_level = _first_present(payload, "purdue_level", "purdueLevel") or existing.purdue_level
    # Tribot's own state wins; this also clears a "missing_from_tribot" flag,
    # since Tribot evidently still has the asset.
    existing.lifecycle_state = _first_present(payload, "lifecycleState") or "active"
    existing.silent_since = _parse_time(payload.get("silentSince")) if existing.lifecycle_state == "silent" else None
    existing.raw = payload
    existing.last_seen_at = now


def decommission_fleet_asset(db: Session, tenant_id, site_id, source_asset_id: str, *, reason: str,
                             decommissioned_by: str | None, decommissioned_at, asset_name: str | None,
                             origin: str, actor_user_id=None) -> FleetAssetTombstone:
    """Removes an asset from the fleet list and every topology link, closes
    its open alerts with the reason (kept for history), records a tombstone
    and an audit entry. Used for Tribot's decommission event and for an admin
    confirming a missing-from-Tribot asset. Does not commit."""
    asset = _find_existing(db, FleetAsset, "source_asset_id", site_id, source_asset_id)
    now = datetime.now(timezone.utc)
    closed = 0
    by_asset = Alert.raw["assetId"].astext == source_asset_id
    if asset is not None:
        by_asset = by_asset | (Alert.asset_id == asset.asset_id)
    open_alerts = select(Alert).where(Alert.site_id == site_id, Alert.status.notin_(CLOSED_ALERT_STATUSES), by_asset)
    for alert in db.execute(open_alerts).scalars():
        alert.status, alert.closed_reason, alert.closed_at = "Closed", f"asset decommissioned: {reason}"[:255], now
        closed += 1
    if asset is not None:
        db.flush()
        db.execute(Alert.__table__.update().where(Alert.asset_id == asset.asset_id).values(asset_id=None))
        asset_name = asset_name or asset.name
    db.execute(FleetTopologyLink.__table__.delete().where(
        FleetTopologyLink.site_id == site_id,
        (FleetTopologyLink.source_asset_id == source_asset_id) | (FleetTopologyLink.target_asset_id == source_asset_id),
    ))
    db.execute(FleetObject.__table__.delete().where(
        FleetObject.site_id == site_id, FleetObject.asset_source_id == source_asset_id,
        FleetObject.object_type.in_(("vulnerability", "software", "patch")),
    ))
    if asset is not None:
        db.delete(asset)
        _remember(db, FleetAsset, site_id, source_asset_id, None)

    tombstone = _find_existing(db, FleetAssetTombstone, "source_asset_id", site_id, source_asset_id)
    if tombstone is None:
        tombstone = FleetAssetTombstone(tenant_id=tenant_id, site_id=site_id, source_asset_id=source_asset_id)
        db.add(tombstone)
        _remember(db, FleetAssetTombstone, site_id, source_asset_id, tombstone)
    tombstone.asset_name, tombstone.reason = asset_name, reason
    tombstone.decommissioned_by, tombstone.decommissioned_at = decommissioned_by, decommissioned_at
    tombstone.origin, tombstone.restored_at = origin, None

    db.add(AuditLog(occurred_at=now, event_type="fleet_asset_decommissioned", result="success",
                    actor_user_id=actor_user_id, target_type="fleet_asset",
                    detail={"site_id": str(site_id), "source_asset_id": source_asset_id, "name": asset_name,
                            "reason": reason, "decommissioned_by": decommissioned_by, "origin": origin,
                            "alerts_closed": closed}))
    return tombstone


def _normalize_topology_link(db: Session, event: IngestedEvent) -> None:
    payload = event.raw_payload.get("payload", {})
    link_id = payload.get("linkId") or event.object_id
    source, target = payload.get("sourceNodeId"), payload.get("targetNodeId")
    if not (link_id and source and target):
        raise ValueError("topology_link event missing linkId/sourceNodeId/targetNodeId")

    existing = _find_existing(db, FleetTopologyLink, "source_link_id", event.site_id, str(link_id))
    if existing is None:
        existing = FleetTopologyLink(tenant_id=event.tenant_id, site_id=event.site_id, source_link_id=str(link_id))
        db.add(existing)
        _remember(db, FleetTopologyLink, event.site_id, str(link_id), existing)
    existing.source_asset_id, existing.target_asset_id = str(source), str(target)
    existing.protocol = payload.get("protocol")
    existing.ports = payload.get("ports") or ([payload["port"]] if payload.get("port") is not None else [])
    existing.first_seen = _parse_time(payload.get("firstSeen"))
    existing.last_seen = _parse_time(payload.get("lastSeen"))
    existing.raw = payload


def _normalize_site_inventory(db: Session, event: IngestedEvent) -> None:
    """Sent by Tribot after a complete full resync: every asset id it holds.
    Assets of the site it no longer lists are flagged missing_from_tribot for
    an admin to confirm (manual section 6 safety net) -- never deleted here.
    A flagged asset that is listed again goes back to active."""
    payload = event.raw_payload.get("payload", {})
    listed = payload.get("assetIds")
    if not isinstance(listed, list):
        raise ValueError("site_inventory event missing assetIds")
    listed = {str(a) for a in listed}
    # Derived records (vulnerabilities, software, patches, IR cases, links) that
    # a complete resync no longer lists are simply gone in Tribot: drop them.
    for object_type, ids in (payload.get("objectIds") or {}).items():
        keep = {str(i) for i in ids}
        if object_type == "topology_link":
            db.execute(FleetTopologyLink.__table__.delete().where(
                FleetTopologyLink.site_id == event.site_id, FleetTopologyLink.source_link_id.notin_(keep)))
        elif object_type in _OBJECT_ID_KEYS:
            db.execute(FleetObject.__table__.delete().where(
                FleetObject.site_id == event.site_id, FleetObject.object_type == object_type,
                FleetObject.source_id.notin_(keep)))
    for asset in db.execute(select(FleetAsset).where(FleetAsset.site_id == event.site_id)).scalars():
        if asset.source_asset_id not in listed and asset.lifecycle_state != "missing_from_tribot":
            asset.lifecycle_state = "missing_from_tribot"
        elif asset.source_asset_id in listed and asset.lifecycle_state == "missing_from_tribot":
            asset.lifecycle_state = (asset.raw or {}).get("lifecycleState") or "active"


def _normalize_alert(db: Session, event: IngestedEvent) -> None:
    payload = event.raw_payload.get("payload", {})
    source_alert_id = _first_present(payload, "alert_id", "alertId") or event.object_id
    if not source_alert_id:
        raise ValueError("alert event missing alert_id")

    existing = _find_existing(db, Alert, "source_alert_id", event.site_id, str(source_alert_id))
    if existing is None:
        existing = Alert(tenant_id=event.tenant_id, site_id=event.site_id, source_alert_id=str(source_alert_id))
        db.add(existing)
        _remember(db, Alert, event.site_id, str(source_alert_id), existing)

    existing.severity = _first_present(payload, "severity") or existing.severity
    existing.status = _first_present(payload, "status") or existing.status
    existing.category = _first_present(payload, "category") or existing.category
    existing.cve_id = _first_present(payload, "cve_id", "cveId") or existing.cve_id
    existing.title = _first_present(payload, "title") or existing.title
    existing.description = _first_present(payload, "description") or existing.description
    existing.raw = payload
    existing.occurred_at = event.occurred_at
    if payload.get("assetId"):
        asset = _find_existing(db, FleetAsset, "source_asset_id", event.site_id, str(payload["assetId"]))
        existing.asset_id = asset.asset_id if asset is not None else None

    if existing.cve_id:
        db.flush()  # correlation needs the alert's id
        correlate_alert(db, existing)


def _normalize_incident(db: Session, event: IngestedEvent) -> None:
    payload = event.raw_payload.get("payload", {})
    source_incident_id = _first_present(payload, "incident_id", "incidentId") or event.object_id
    if not source_incident_id:
        raise ValueError("incident event missing incident_id")

    existing = _find_existing(db, Incident, "source_incident_id", event.site_id, str(source_incident_id))
    if existing is None:
        existing = Incident(tenant_id=event.tenant_id, site_id=event.site_id, source_incident_id=str(source_incident_id))
        db.add(existing)
        _remember(db, Incident, event.site_id, str(source_incident_id), existing)

    existing.incident_source = _first_present(payload, "incident_source", "incidentSource") or existing.incident_source or "tribot"
    existing.ecc_incident_id = _first_present(payload, "ecc_incident_id", "eccIncidentId") or existing.ecc_incident_id
    existing.tribot_incident_id = _first_present(payload, "tribot_incident_id", "tribotIncidentId") or str(source_incident_id)
    existing.title = _first_present(payload, "title") or existing.title
    existing.description = _first_present(payload, "description") or existing.description
    existing.category = _first_present(payload, "category") or existing.category
    existing.type = _first_present(payload, "type") or existing.type
    existing.severity = _first_present(payload, "severity") or existing.severity
    existing.priority = _first_present(payload, "priority") or existing.priority
    existing.status = _first_present(payload, "status") or existing.status
    existing.owner = _first_present(payload, "owner") or existing.owner
    existing.alert_ids = _first_present(payload, "alert_ids", "alertIds") or existing.alert_ids
    existing.finding_ids = _first_present(payload, "finding_ids", "findingIds") or existing.finding_ids
    existing.asset_ids = _first_present(payload, "asset_ids", "assetIds") or existing.asset_ids
    existing.impact = _first_present(payload, "impact") or existing.impact


def _normalize_remediation(db: Session, event: IngestedEvent) -> None:
    payload = event.raw_payload.get("payload", {})
    source_remediation_id = _first_present(payload, "remediation_id", "remediationId") or event.object_id
    if not source_remediation_id:
        raise ValueError("remediation event missing remediation_id")

    existing = _find_existing(db, Remediation, "source_remediation_id", event.site_id, str(source_remediation_id))
    if existing is None:
        existing = Remediation(tenant_id=event.tenant_id, site_id=event.site_id, source_remediation_id=str(source_remediation_id))
        db.add(existing)
        _remember(db, Remediation, event.site_id, str(source_remediation_id), existing)

    existing.type = _first_present(payload, "type") or existing.type
    existing.title = _first_present(payload, "title") or existing.title
    existing.description = _first_present(payload, "description") or existing.description
    existing.owner = _first_present(payload, "owner") or existing.owner
    existing.status = _first_present(payload, "status") or existing.status
    existing.planned_date = _first_present(payload, "planned_date", "plannedDate") or existing.planned_date
    existing.implementation_date = _first_present(payload, "implementation_date", "implementationDate") or existing.implementation_date
    existing.validation_date = _first_present(payload, "validation_date", "validationDate") or existing.validation_date
    existing.closure_date = _first_present(payload, "closure_date", "closureDate") or existing.closure_date

    # Append-only plan history (FRD Section 10/29): if Tribot sends its full
    # history array, only ever grow ours to match (never shrink/overwrite
    # entries we already have); if it sends one new entry, append it.
    incoming_history = _first_present(payload, "plan_history", "planHistory")
    if isinstance(incoming_history, list) and len(incoming_history) > len(existing.plan_history or []):
        existing.plan_history = incoming_history
        existing.current_plan_version = len(incoming_history)


_NORMALIZERS = {
    "asset": _normalize_asset,
    "alert": _normalize_alert,
    "remediation": _normalize_remediation,
    "incident": _normalize_incident,
    "ir_case": lambda db, event: (_normalize_incident(db, event),
                                  _store_object(db, event, "ir_case", event.raw_payload.get("payload", {}))),
    "topology_link": _normalize_topology_link,
    "site_inventory": _normalize_site_inventory,
    "vulnerability": _normalize_object,
    "software": _normalize_object,
    "patch": _normalize_object,
    "site_config": _normalize_object,
}


DEFAULT_BATCH_SIZE = 1000


def _claim_pending(db: Session, batch_size: int, event_ids=None) -> list[IngestedEvent]:
    query = (
        select(IngestedEvent)
        .where(IngestedEvent.process_status == "pending")
        .order_by(IngestedEvent.received_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    if event_ids is not None:
        query = query.where(IngestedEvent.event_id.in_(event_ids))
    return db.execute(query).scalars().all()


def _apply(db: Session, pending: list[IngestedEvent], isolate: bool) -> dict[str, int]:
    """isolate=False: fast path, no savepoints; a missing object id (the
    normalizers' ValueError, raised before they touch the session) fails just
    that event, any other error propagates so the caller can retry the batch
    isolated. isolate=True: one SAVEPOINT per event, so any failure -- a
    database error included -- rolls back only that event."""
    counts = {"processed": 0, "failed": 0, "skipped": 0}
    now = datetime.now(timezone.utc)
    for event in pending:
        normalizer = _NORMALIZERS.get(event.object_type)
        if normalizer is None:
            event.process_status = "skipped"
            event.error_message = f"no normalizer for object_type={event.object_type!r} yet"
            counts["skipped"] += 1
            continue

        try:
            if isolate:
                with db.begin_nested():
                    normalizer(db, event)
                    db.flush()
            else:
                normalizer(db, event)
            event.process_status = "processed"
            event.processed_at = now
            counts["processed"] += 1
        except EventIgnored as exc:
            event.process_status = "skipped"
            event.error_message = str(exc)
            counts["skipped"] += 1
        except Exception as exc:  # noqa: BLE001 -- one bad event must not stop the batch
            if not isolate and not isinstance(exc, ValueError):
                raise
            logger.warning("failed to normalize ingested_event %s: %s", event.event_id, exc)
            event.process_status = "failed"
            event.error_message = str(exc)
            counts["failed"] += 1
    return counts


def process_pending_events(db: Session, batch_size: int = DEFAULT_BATCH_SIZE) -> dict[str, int]:
    """Processes up to `batch_size` pending events, oldest first, in ONE
    transaction. Every fleet row the batch touches is loaded up front with one
    query per model (_prefetch), the events are applied in memory, and the
    batch is written with one flush and one commit -- instead of a SELECT,
    a SAVEPOINT and a commit per event. That is what lets one USV keep up
    with hundreds of sites.

    If the batch fails at the database (e.g. a value too long for a column),
    it is rolled back and re-run with a SAVEPOINT per event, so the bad
    event is marked 'failed' (left for inspection) and the rest still land.

    Rows are claimed with FOR UPDATE SKIP LOCKED, so several workers (e.g.
    uvicorn --workers N, each running this loop) take disjoint batches and an
    event is never normalized twice."""
    pending = _claim_pending(db, batch_size)
    if not pending:
        return {"processed": 0, "failed": 0, "skipped": 0}

    event_ids = [e.event_id for e in pending]
    db.info[_CACHE_KEY] = {}
    try:
        _prefetch(db, pending)
        counts = _apply(db, pending, isolate=False)
        db.commit()
        return counts
    except Exception:  # noqa: BLE001 -- fall back to isolating the bad event
        db.rollback()
        logger.warning("ingestion batch of %d failed as a whole; retrying event by event", len(event_ids),
                       exc_info=True)
    finally:
        db.info.pop(_CACHE_KEY, None)

    pending = _claim_pending(db, batch_size, event_ids)
    counts = _apply(db, pending, isolate=True)
    db.commit()
    return counts


def purge_processed_events(db: Session, older_than_days: int, chunk_size: int = 5000) -> int:
    """Deletes processed/skipped staging rows older than `older_than_days`.
    Their content already lives in the fleet_* tables; keeping every raw
    envelope forever from hundreds of sites would grow without bound. Failed
    rows are kept for inspection. Deletes in chunks to keep transactions short."""
    total = 0
    while True:
        deleted = db.execute(
            text(
                "DELETE FROM ingested_event WHERE event_id IN ("
                " SELECT event_id FROM ingested_event"
                " WHERE process_status IN ('processed', 'skipped')"
                " AND received_at < now() - make_interval(days => :days)"
                " LIMIT :chunk)"
            ),
            {"days": older_than_days, "chunk": chunk_size},
        ).rowcount
        db.commit()
        total += deleted
        if deleted < chunk_size:
            return total
