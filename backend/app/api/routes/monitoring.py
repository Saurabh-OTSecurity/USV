"""USV monitoring API (USV O&M Manual section 7): USV-generated alerts,
platform health summary, planned downtime, monitoring limits and in-app
notifications."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.rbac import (
    USV_BU_ADMIN, USV_CUSTOMER_ADMIN, USV_PLATFORM_ADMIN, USV_SITE_ADMIN, get_current_user, get_db, require_role,
)
from app.models.ingested_event import IngestedEvent
from app.models.monitoring import MonitoringSetting, PlannedDowntime, SiteState, UsvAlert, UsvNotification
from app.models.site import Site
from app.models.usv_user import UsvUser
from app.services.access_scope import CUSTOMER_WIDE_ROLES, can_manage_site, can_view_site, visible_site_ids
from app.services.monitoring import alerts as alert_service
from app.services.monitoring import checks
from app.services.monitoring.rules import effective_settings

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])

ADMINS = (USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN, USV_BU_ADMIN, USV_SITE_ADMIN)

# What a customer or site may set, within the platform's bounds (manual: "Limits can
# be changed per site or per customer, within what the platform admin allows").
BOUNDS = {
    "check_in_minutes": (5, 240),
    "silent_after_intervals": (1, 20),
    "disconnected_after_intervals": (1, 40),
    "first_data_hours": (1, 168),
    "escalation_minutes": (5, 1440),
}


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": f"{what} not found"}})


def _require_site_admin(db: Session, user: UsvUser, site_id: uuid.UUID) -> Site:
    site = db.get(Site, site_id)
    if site is None or not can_manage_site(db, user, site_id):
        raise _not_found("Site")
    return site


# ── alerts ──

class UsvAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    usv_alert_id: uuid.UUID
    site_id: uuid.UUID | None
    rule_id: str
    category: str
    severity: str
    title: str
    detail: dict
    status: str
    event_only: bool
    occurrence_count: int
    opened_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    closed_at: datetime | None
    escalation_level: int


@router.get("/alerts", response_model=list[UsvAlertResponse])
def list_usv_alerts(
    response: Response,
    status: Optional[str] = Query(None, pattern="^(open|acknowledged|closed|active)$"),
    category: Optional[str] = Query(None, pattern="^(Site|Platform|Security)$"),
    severity: Optional[str] = Query(None, pattern="^(Info|Warning|Critical)$"),
    siteId: Optional[uuid.UUID] = None,
    ruleId: Optional[str] = None,
    includeEvents: bool = True,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[UsvAlertResponse]:
    """status=active means open or acknowledged (not closed)."""
    query = select(UsvAlert)
    visible = visible_site_ids(db, current_user)
    if visible is not None:
        # site-scoped people see their sites' alerts; platform/security
        # alerts (no site) are for customer-wide roles
        query = query.where(UsvAlert.site_id.in_(visible))
    if status == "active":
        query = query.where(UsvAlert.status != "closed")
    elif status:
        query = query.where(UsvAlert.status == status)
    for column, value in ((UsvAlert.category, category), (UsvAlert.severity, severity),
                          (UsvAlert.site_id, siteId), (UsvAlert.rule_id, ruleId)):
        if value is not None:
            query = query.where(column == value)
    if not includeEvents:
        query = query.where(UsvAlert.event_only.is_(False))
    response.headers["X-Total-Count"] = str(db.execute(select(func.count()).select_from(query.subquery())).scalar())
    rows = db.execute(query.order_by(UsvAlert.last_seen_at.desc()).offset(offset).limit(limit)).scalars()
    return [UsvAlertResponse.model_validate(r) for r in rows]


@router.post("/alerts/{alert_id}/acknowledge", response_model=UsvAlertResponse)
def acknowledge_usv_alert(alert_id: uuid.UUID, db: Session = Depends(get_db),
                          current_user: UsvUser = Depends(require_role(*ADMINS))) -> UsvAlertResponse:
    """Stops escalation. A rule with no auto-close (rejected connections,
    SU-08) is also closed here: the admin has looked at it."""
    alert = db.get(UsvAlert, alert_id)
    if alert is None or (alert.site_id and not can_manage_site(db, current_user, alert.site_id)) \
            or (alert.site_id is None and current_user.role not in CUSTOMER_WIDE_ROLES):
        raise _not_found("Alert")
    alert_service.acknowledge(db, alert, current_user)
    if alert.rule_id == "SU-08":
        alert.status, alert.closed_at = "closed", datetime.now(timezone.utc)
    db.commit()
    db.refresh(alert)
    return UsvAlertResponse.model_validate(alert)


# ── platform health summary (data for the proposed Platform health page) ──

@router.get("/health-summary")
def health_summary(db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)) -> dict:
    now = datetime.now(timezone.utc)
    visible = visible_site_ids(db, current_user)
    sites = {s.site_id: s for s in db.execute(select(Site)).scalars() if visible is None or s.site_id in visible}
    states = {s.site_id: s for s in db.execute(select(SiteState)).scalars()}
    per_site = []
    counts = {"healthy": 0, "silent": 0, "disconnected": 0, "waiting_first_data": 0}
    for site_id, site in sites.items():
        st = states.get(site_id)
        state = st.state if st else "waiting_first_data"
        counts[state] = counts.get(state, 0) + 1
        per_site.append({"site_id": str(site_id), "site_code": site.site_code, "name": site.name, "state": state,
                         "state_since": st.state_since.isoformat() if st else None,
                         "last_contact_at": st.last_contact_at.isoformat() if st and st.last_contact_at else None})
    if visible is not None:
        # platform internals are for customer-wide roles
        return {"generated_at": now.isoformat(), "site_counts": counts,
                "sites": sorted(per_site, key=lambda s: s["site_code"])}
    pending, oldest = db.execute(select(func.count(), func.min(IngestedEvent.received_at)).where(
        IngestedEvent.process_status == "pending")).one()
    open_alerts = dict(db.execute(select(UsvAlert.severity, func.count()).where(
        UsvAlert.status != "closed").group_by(UsvAlert.severity)).all())
    return {
        "generated_at": now.isoformat(),
        "site_counts": counts,
        "sites": sorted(per_site, key=lambda s: s["site_code"]),
        "ingestion": {"pending": pending,
                      "delay_seconds": round((now - oldest).total_seconds(), 1) if oldest else 0},
        "database": checks.database_probe(db),
        "database_disk": checks.disk_probe(),
        "certificate": checks.certificate_probe(now),
        "backup": checks.backup_probe(now),
        "api": checks.api_errors.snapshot(),
        "open_alerts_by_severity": open_alerts,
    }


# ── planned downtime ──

class DowntimeCreate(BaseModel):
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def _window(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class DowntimeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    downtime_id: uuid.UUID
    site_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    reason: str
    created_by: uuid.UUID | None


@router.get("/sites/{site_id}/downtime", response_model=list[DowntimeResponse])
def list_downtime(site_id: uuid.UUID, db: Session = Depends(get_db),
                  current_user: UsvUser = Depends(get_current_user)) -> list[DowntimeResponse]:
    if not can_view_site(db, current_user, site_id):
        raise _not_found("Site")
    rows = db.execute(select(PlannedDowntime).where(PlannedDowntime.site_id == site_id)
                      .order_by(PlannedDowntime.starts_at.desc())).scalars()
    return [DowntimeResponse.model_validate(r) for r in rows]


@router.post("/sites/{site_id}/downtime", response_model=DowntimeResponse, status_code=201)
def create_downtime(site_id: uuid.UUID, payload: DowntimeCreate, db: Session = Depends(get_db),
                    current_user: UsvUser = Depends(require_role(*ADMINS))) -> DowntimeResponse:
    """While the window is active the site's silent/disconnected alerts stay quiet."""
    _require_site_admin(db, current_user, site_id)
    row = PlannedDowntime(site_id=site_id, starts_at=payload.starts_at, ends_at=payload.ends_at,
                          reason=payload.reason, created_by=current_user.user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return DowntimeResponse.model_validate(row)


@router.delete("/sites/{site_id}/downtime/{downtime_id}", status_code=204)
def delete_downtime(site_id: uuid.UUID, downtime_id: uuid.UUID, db: Session = Depends(get_db),
                    current_user: UsvUser = Depends(require_role(*ADMINS))) -> Response:
    _require_site_admin(db, current_user, site_id)
    row = db.get(PlannedDowntime, downtime_id)
    if row is None or row.site_id != site_id:
        raise _not_found("Downtime window")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


# ── monitoring limits ──

class MonitoringLimits(BaseModel):
    check_in_minutes: int | None = None
    silent_after_intervals: int | None = None
    disconnected_after_intervals: int | None = None
    first_data_hours: int | None = None
    escalation_minutes: int | None = None

    @model_validator(mode="after")
    def _bounds(self):
        for field, (low, high) in BOUNDS.items():
            value = getattr(self, field)
            if value is not None and not low <= value <= high:
                raise ValueError(f"{field} must be between {low} and {high}")
        if (self.silent_after_intervals and self.disconnected_after_intervals
                and self.disconnected_after_intervals <= self.silent_after_intervals):
            raise ValueError("disconnected_after_intervals must be greater than silent_after_intervals")
        return self


def _limits_out(db: Session, site_id: uuid.UUID | None) -> dict:
    row = db.execute(select(MonitoringSetting).where(
        MonitoringSetting.site_id.is_(None) if site_id is None else MonitoringSetting.site_id == site_id
    )).scalar_one_or_none()
    return {
        "site_id": str(site_id) if site_id else None,
        "configured": {f: getattr(row, f) if row else None for f in BOUNDS},
        "effective": effective_settings(db)(site_id),
        "bounds": BOUNDS,
    }


def _save_limits(db: Session, site_id: uuid.UUID | None, payload: MonitoringLimits) -> None:
    row = db.execute(select(MonitoringSetting).where(
        MonitoringSetting.site_id.is_(None) if site_id is None else MonitoringSetting.site_id == site_id
    )).scalar_one_or_none()
    if row is None:
        row = MonitoringSetting(site_id=site_id)
        db.add(row)
    for field in BOUNDS:
        setattr(row, field, getattr(payload, field))
    db.commit()


@router.get("/settings")
def get_default_limits(db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)) -> dict:
    """This customer's defaults (fields left empty use the platform default)."""
    return _limits_out(db, None)


@router.put("/settings")
def put_default_limits(payload: MonitoringLimits, db: Session = Depends(get_db),
                       current_user: UsvUser = Depends(require_role(USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN))) -> dict:
    _save_limits(db, None, payload)
    return _limits_out(db, None)


@router.get("/sites/{site_id}/settings")
def get_site_limits(site_id: uuid.UUID, db: Session = Depends(get_db),
                    current_user: UsvUser = Depends(get_current_user)) -> dict:
    if db.get(Site, site_id) is None or not can_view_site(db, current_user, site_id):
        raise _not_found("Site")
    return _limits_out(db, site_id)


@router.put("/sites/{site_id}/settings")
def put_site_limits(site_id: uuid.UUID, payload: MonitoringLimits, db: Session = Depends(get_db),
                    current_user: UsvUser = Depends(require_role(*ADMINS))) -> dict:
    _require_site_admin(db, current_user, site_id)
    _save_limits(db, site_id, payload)
    return _limits_out(db, site_id)


# ── in-app notifications ──

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notification_id: uuid.UUID
    usv_alert_id: uuid.UUID | None
    level: str
    title: str
    created_at: datetime
    read_at: datetime | None


@router.get("/notifications", response_model=list[NotificationResponse])
def my_notifications(unreadOnly: bool = False, limit: int = Query(100, ge=1, le=500),
                     db: Session = Depends(get_db),
                     current_user: UsvUser = Depends(get_current_user)) -> list[NotificationResponse]:
    query = select(UsvNotification).where(UsvNotification.user_id == current_user.user_id)
    if unreadOnly:
        query = query.where(UsvNotification.read_at.is_(None))
    rows = db.execute(query.order_by(UsvNotification.created_at.desc()).limit(limit)).scalars()
    return [NotificationResponse.model_validate(r) for r in rows]


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(notification_id: uuid.UUID, db: Session = Depends(get_db),
                           current_user: UsvUser = Depends(get_current_user)) -> NotificationResponse:
    row = db.get(UsvNotification, notification_id)
    if row is None or row.user_id != current_user.user_id:
        raise _not_found("Notification")
    row.read_at = row.read_at or datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return NotificationResponse.model_validate(row)
