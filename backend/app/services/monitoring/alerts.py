"""Raising, updating and clearing USV-generated alerts, and in-app
notification with escalation (USV O&M Manual section 7, "How these alerts
behave").

- raise_alert(): one not-closed alert per dedupe_key. Raising an existing
  condition bumps occurrence_count/last_seen and may raise its severity
  (Warning -> Critical); it never creates a second row.
- clear_alert(): closes it on recovery ("closes by itself").
- record_event(): an event-only entry (site added, token issued...),
  created closed, for history.
- escalate(): notifies the site's admins when an alert opens; if nobody
  acknowledges within the escalation time, the next level up is notified.
  The levels are the manual's section 11 chain; levels with no people
  configured are skipped (customer and BU admin roles arrive with the
  organization structure work).
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import USV_PLATFORM_ADMIN, USV_SITE_ADMIN
from app.models.monitoring import UsvAlert, UsvNotification
from app.models.site import Site
from app.models.usv_user import UsvUser
from app.models.usv_user_site import UsvUserSite

SEVERITY_ORDER = {"Info": 0, "Warning": 1, "Critical": 2}

# Escalation chain, lowest first. A role missing from the deployment simply
# has no recipients and is skipped.
ESCALATION_LEVELS = (
    ("site_admin", (USV_SITE_ADMIN,)),
    ("bu_admin", ("usv_bu_admin",)),
    ("customer_admin", ("usv_customer_admin",)),
    ("platform_admin", (USV_PLATFORM_ADMIN,)),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def open_alert(db: Session, dedupe_key: str) -> UsvAlert | None:
    return db.execute(
        select(UsvAlert).where(UsvAlert.dedupe_key == dedupe_key, UsvAlert.status != "closed")
    ).scalar_one_or_none()


def raise_alert(db: Session, *, rule_id: str, dedupe_key: str, category: str, severity: str, title: str,
                site_id: uuid.UUID | None = None, detail: dict | None = None,
                now: datetime | None = None) -> tuple[UsvAlert, bool]:
    """Returns (alert, newly_opened)."""
    now = now or _now()
    alert = open_alert(db, dedupe_key)
    if alert is not None:
        alert.last_seen_at = now
        alert.occurrence_count += 1
        alert.title = title
        if detail is not None:
            alert.detail = detail
        if SEVERITY_ORDER[severity] > SEVERITY_ORDER.get(alert.severity, 0):
            alert.severity = severity
        return alert, False
    alert = UsvAlert(rule_id=rule_id, dedupe_key=dedupe_key, category=category, severity=severity, title=title,
                     site_id=site_id, detail=detail or {}, status="open", opened_at=now, last_seen_at=now)
    db.add(alert)
    db.flush()
    if severity != "Info":
        _notify_level(db, alert, 0, now)
    return alert, True


def clear_alert(db: Session, dedupe_key: str, now: datetime | None = None, note: str | None = None) -> UsvAlert | None:
    alert = open_alert(db, dedupe_key)
    if alert is not None:
        alert.status, alert.closed_at = "closed", now or _now()
        if note:
            alert.detail = {**(alert.detail or {}), "closed_note": note}
    return alert


def record_event(db: Session, *, rule_id: str, category: str, title: str, severity: str = "Info",
                 site_id: uuid.UUID | None = None, detail: dict | None = None,
                 now: datetime | None = None) -> UsvAlert:
    now = now or _now()
    alert = UsvAlert(rule_id=rule_id, dedupe_key=f"{rule_id}|event|{uuid.uuid4().hex}", category=category,
                     severity=severity, title=title, site_id=site_id, detail=detail or {}, status="closed",
                     event_only=True, opened_at=now, last_seen_at=now, closed_at=now)
    db.add(alert)
    db.flush()
    if severity != "Info":
        _notify_level(db, alert, 0, now)
    return alert


def acknowledge(db: Session, alert: UsvAlert, user: UsvUser, now: datetime | None = None) -> UsvAlert:
    if alert.status == "open":
        alert.status, alert.acknowledged_at, alert.acknowledged_by = "acknowledged", now or _now(), user.user_id
    return alert


def _recipients(db: Session, roles: tuple, site_id: uuid.UUID | None) -> list[UsvUser]:
    """People at one level who are responsible for this alert: site admins
    of its site, BU admins of its site's business unit, every customer or
    platform admin. A site-level level has nobody for a platform alert."""
    users = db.execute(select(UsvUser).where(UsvUser.role.in_(roles), UsvUser.status == "active")).scalars().all()
    if USV_SITE_ADMIN in roles:
        if site_id is None:
            return []
        assigned = {row.user_id for row in db.execute(
            select(UsvUserSite).where(UsvUserSite.site_id == site_id)).scalars()}
        return [u for u in users if u.site_id == site_id or u.user_id in assigned]
    if "usv_bu_admin" in roles:
        site = db.get(Site, site_id) if site_id else None
        if site is None:
            return []
        return [u for u in users if u.business_unit_id == site.business_unit_id]
    return list(users)


def _notify_level(db: Session, alert: UsvAlert, start_level: int, now: datetime) -> None:
    """Notifies the first level at or above start_level that has anyone in it."""
    for level in range(start_level, len(ESCALATION_LEVELS)):
        name, roles = ESCALATION_LEVELS[level]
        users = _recipients(db, roles, alert.site_id)
        if users:
            for user in users:
                db.add(UsvNotification(user_id=user.user_id, usv_alert_id=alert.usv_alert_id, level=name,
                                       title=f"[{alert.severity}] {alert.title}", created_at=now))
            alert.escalation_level, alert.escalated_at = level, now
            return


def escalate_unacknowledged(db: Session, escalation_minutes_for, now: datetime | None = None) -> int:
    """For every open (not acknowledged) Warning/Critical alert whose current
    level has had its escalation time, notify the next level up. Returns how
    many alerts escalated. escalation_minutes_for(site_id) gives the limit."""
    now = now or _now()
    escalated = 0
    candidates = db.execute(select(UsvAlert).where(
        UsvAlert.status == "open", UsvAlert.event_only.is_(False), UsvAlert.severity != "Info",
        UsvAlert.escalation_level < len(ESCALATION_LEVELS) - 1)).scalars().all()
    for alert in candidates:
        since = alert.escalated_at or alert.opened_at
        if now - since >= timedelta(minutes=escalation_minutes_for(alert.site_id)):
            before = alert.escalation_level
            _notify_level(db, alert, before + 1, now)
            if alert.escalation_level > before:
                escalated += 1
            else:
                alert.escalation_level = len(ESCALATION_LEVELS) - 1  # nobody above: stop trying
    return escalated
