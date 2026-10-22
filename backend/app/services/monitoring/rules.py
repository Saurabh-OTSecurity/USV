"""USV's own alert rules (USV O&M Manual section 7, backlog 18).

run_monitoring(db) evaluates every rule once; app/main.py runs it every
minute. Rule ids follow the manual:

  Sites     SU-03 waiting for first data   SU-04 onboarded (event)
            SU-05 silent                    SU-06 disconnected
            SU-07 reconnected (event)       SU-08 rejected connections
            SU-09 clock skew                SU-10 volume anomaly
            (SU-01 site added and SU-02 token changes are events raised by
            the site/token routes -- see site_added()/token_changed())
  Platform  PL-01 ingestion backlog  PL-02 failed events  PL-03 worker not running
            PL-04 database slow      PL-05 database disk  PL-06 certificate expiry
            PL-07 API errors         PL-08 backup missed
  Security  SE-01 repeated failed logins

A site's "contact" is the newest of its tokens' last_used_at (any push or
heartbeat refreshes it) and its last heartbeat health. Limits come from
effective_settings(): site override -> customer default -> platform config.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.fleet_asset import FleetAsset
from app.models.fleet_lifecycle import SiteHealth
from app.models.ingested_event import IngestedEvent
from app.models.ingestion_token import IngestionToken
from app.models.monitoring import IngestionAuthFailure, MonitoringSetting, PlannedDowntime, SiteState
from app.models.site import Site
from app.services.monitoring import checks
from app.services import identity_flows
from app.services.monitoring.alerts import clear_alert, escalate_unacknowledged, raise_alert, record_event

logger = logging.getLogger("app.monitoring")

SETTING_FIELDS = {
    "check_in_minutes": "monitor_check_in_minutes",
    "silent_after_intervals": "monitor_silent_after_intervals",
    "disconnected_after_intervals": "monitor_disconnected_after_intervals",
    "first_data_hours": "monitor_first_data_hours",
    "escalation_minutes": "monitor_escalation_minutes",
}

VOLUME_CHECK_EVERY = timedelta(minutes=15)
_last_volume_check: dict = {}


def effective_settings(db: Session):
    """Returns f(site_id) -> {field: value}, resolving each field from the
    site's row, then the customer default row, then platform config."""
    rows = db.execute(select(MonitoringSetting)).scalars().all()
    default = next((r for r in rows if r.site_id is None), None)
    by_site = {r.site_id: r for r in rows if r.site_id is not None}

    def resolve(site_id):
        out = {}
        for field, config_name in SETTING_FIELDS.items():
            value = None
            if site_id in by_site:
                value = getattr(by_site[site_id], field)
            if value is None and default is not None:
                value = getattr(default, field)
            out[field] = value if value is not None else getattr(settings, config_name)
        return out
    return resolve


def _in_downtime(db: Session, site_id, now: datetime) -> PlannedDowntime | None:
    return db.execute(select(PlannedDowntime).where(
        PlannedDowntime.site_id == site_id, PlannedDowntime.starts_at <= now, PlannedDowntime.ends_at > now,
    )).scalars().first()


def _fmt_duration(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


# ── event hooks called from routes ──

def site_added(db: Session, site: Site) -> None:
    record_event(db, rule_id="SU-01", category="Site", title=f"Site added: {site.site_code} {site.name}",
                 site_id=site.site_id, detail={"site_code": site.site_code})


def token_changed(db: Session, site_id, action: str, token_id) -> None:
    """action: issued / revoked."""
    site = db.get(Site, site_id)
    record_event(db, rule_id="SU-02", category="Site",
                 title=f"Ingestion token {action} for {site.site_code if site else site_id}",
                 site_id=site_id, detail={"action": action, "token_id": str(token_id)})


# ── site rules ──

def evaluate_sites(db: Session, now: datetime, limits) -> None:
    sites = db.execute(select(Site)).scalars().all()
    tokens = db.execute(select(IngestionToken)).scalars().all()
    health = {h.site_id: h for h in db.execute(select(SiteHealth)).scalars()}
    states = {s.site_id: s for s in db.execute(select(SiteState)).scalars()}

    tokens_by_site: dict = {}
    for t in tokens:
        tokens_by_site.setdefault(t.site_id, []).append(t)

    for site in sites:
        cfg = limits(site.site_id)
        site_tokens = tokens_by_site.get(site.site_id, [])
        contacts = [t.last_used_at for t in site_tokens if t.last_used_at]
        if site.site_id in health:
            contacts.append(health[site.site_id].received_at)
        last_contact = max(contacts) if contacts else None

        state = states.get(site.site_id)
        if state is None:
            state = SiteState(site_id=site.site_id, state="waiting_first_data", state_since=now)
            db.add(state)
            states[site.site_id] = state
        state.last_contact_at = last_contact

        # first data: anything staged from the site, or fleet data already held
        if state.first_data_at is None:
            first = db.execute(select(func.min(IngestedEvent.received_at)).where(
                IngestedEvent.site_id == site.site_id)).scalar()
            if first is None and db.execute(select(FleetAsset.asset_id).where(
                    FleetAsset.site_id == site.site_id).limit(1)).first():
                first = now
            if first is not None:
                state.first_data_at = first
                clear_alert(db, f"SU-03|{site.site_id}", now)
                record_event(db, rule_id="SU-04", category="Site", site_id=site.site_id,
                             title=f"Site onboarded: {site.site_code} sent its first data",
                             detail={"first_data_at": first.isoformat()})

        if state.first_data_at is None:
            active = [t for t in site_tokens if t.status == "active"]
            issued = min((t.created_at for t in active), default=None)
            if issued is not None and now - issued >= timedelta(hours=cfg["first_data_hours"]):
                raise_alert(db, rule_id="SU-03", dedupe_key=f"SU-03|{site.site_id}", category="Site",
                            severity="Warning", site_id=site.site_id,
                            title=f"Site waiting for first data: {site.site_code}",
                            detail={"token_issued_at": issued.isoformat(), "limit_hours": cfg["first_data_hours"]},
                            now=now)
            continue

        interval = timedelta(minutes=cfg["check_in_minutes"])
        age = now - last_contact if last_contact else timedelta.max
        if last_contact and age < interval * cfg["silent_after_intervals"]:
            new_state = "healthy"
        elif last_contact and age < interval * cfg["disconnected_after_intervals"]:
            new_state = "silent"
        else:
            new_state = "disconnected"

        downtime = _in_downtime(db, site.site_id, now)
        if new_state == "healthy":
            if state.state in ("silent", "disconnected"):
                record_event(db, rule_id="SU-07", category="Site", site_id=site.site_id,
                             title=f"Site reconnected: {site.site_code} after {_fmt_duration(now - state.state_since)}",
                             detail={"was": state.state, "out_since": state.state_since.isoformat()})
            clear_alert(db, f"SU-05|{site.site_id}", now)
            clear_alert(db, f"SU-06|{site.site_id}", now)
        elif downtime is not None:
            note = f"planned downtime until {downtime.ends_at.isoformat()}: {downtime.reason}"
            clear_alert(db, f"SU-05|{site.site_id}", now, note)
            clear_alert(db, f"SU-06|{site.site_id}", now, note)
        else:
            detail = {"last_contact_at": last_contact.isoformat() if last_contact else None,
                      "check_in_minutes": cfg["check_in_minutes"]}
            if new_state == "disconnected":
                clear_alert(db, f"SU-05|{site.site_id}", now, "escalated to disconnected")
                raise_alert(db, rule_id="SU-06", dedupe_key=f"SU-06|{site.site_id}", category="Site",
                            severity="Critical", site_id=site.site_id, detail=detail, now=now,
                            title=f"Site disconnected: {site.site_code} (no contact for {_fmt_duration(age) if last_contact else 'ever'})")
            else:
                raise_alert(db, rule_id="SU-05", dedupe_key=f"SU-05|{site.site_id}", category="Site",
                            severity="Warning", site_id=site.site_id, detail=detail, now=now,
                            title=f"Site silent: {site.site_code} (no contact for {_fmt_duration(age)})")

        if new_state != state.state:
            state.state, state.state_since = new_state, now

        # SU-09 clock skew, judged only on reasonably fresh health
        h = health.get(site.site_id)
        if h is not None and h.clock_skew_seconds is not None and now - h.received_at < interval * 2:
            key = f"SU-09|{site.site_id}"
            if abs(h.clock_skew_seconds) > settings.monitor_clock_skew_seconds:
                raise_alert(db, rule_id="SU-09", dedupe_key=key, category="Site", severity="Warning",
                            site_id=site.site_id, now=now,
                            title=f"Clock skew at {site.site_code}: {round(h.clock_skew_seconds / 60, 1)} min",
                            detail={"clock_skew_seconds": h.clock_skew_seconds})
            else:
                clear_alert(db, key, now)


def evaluate_rejected_connections(db: Session, now: datetime) -> None:
    """SU-08: repeated refused requests for a site's token, or any use of a
    revoked token. Closes only when an admin acknowledges (no auto-close)."""
    since = now - timedelta(minutes=10)
    rows = db.execute(select(IngestionAuthFailure.site_id, IngestionAuthFailure.reason, func.count()).where(
        IngestionAuthFailure.occurred_at >= since, IngestionAuthFailure.site_id.isnot(None),
    ).group_by(IngestionAuthFailure.site_id, IngestionAuthFailure.reason)).all()
    per_site: dict = {}
    for site_id, reason, count in rows:
        per_site.setdefault(site_id, {})[reason] = count
    for site_id, reasons in per_site.items():
        total = sum(reasons.values())
        revoked = reasons.get("revoked", 0)
        if revoked or total >= settings.monitor_rejected_connections_limit:
            site = db.get(Site, site_id)
            raise_alert(db, rule_id="SU-08", dedupe_key=f"SU-08|{site_id}", category="Site",
                        severity="Critical" if revoked else "Warning", site_id=site_id, now=now,
                        title=(f"Revoked token used by {site.site_code}" if revoked else
                               f"Rejected connections from {site.site_code}: {total} in 10 min"),
                        detail={"last_10_min": reasons})


def evaluate_volume(db: Session, now: datetime) -> None:
    """SU-10: a site's event count in the last hour against its own average
    hourly count over the previous 7 days (staging retention). Runs every 15
    minutes; sites below the minimum baseline are too quiet to judge."""
    hour_ago, week_ago = now - timedelta(hours=1), now - timedelta(days=7)
    recent = dict(db.execute(select(IngestedEvent.site_id, func.count()).where(
        IngestedEvent.received_at >= hour_ago).group_by(IngestedEvent.site_id)).all())
    baseline_rows = db.execute(select(IngestedEvent.site_id, func.count(), func.min(IngestedEvent.received_at)).where(
        IngestedEvent.received_at >= week_ago, IngestedEvent.received_at < hour_ago,
    ).group_by(IngestedEvent.site_id)).all()
    for site_id, count, oldest in baseline_rows:
        hours = max(1.0, (hour_ago - oldest).total_seconds() / 3600)
        baseline = count / hours
        key = f"SU-10|{site_id}"
        if baseline < settings.monitor_volume_min_baseline_per_hour or hours < 24:
            clear_alert(db, key, now)
            continue
        current = recent.get(site_id, 0)
        if current < baseline * settings.monitor_volume_drop_ratio or current > baseline * settings.monitor_volume_spike_ratio:
            site = db.get(Site, site_id)
            direction = "dropped" if current < baseline else "jumped"
            raise_alert(db, rule_id="SU-10", dedupe_key=key, category="Site", severity="Warning",
                        site_id=site_id, now=now,
                        title=f"Event volume {direction} at {site.site_code}: {current}/h vs normal {round(baseline)}/h",
                        detail={"last_hour": current, "normal_per_hour": round(baseline, 1)})
        else:
            clear_alert(db, key, now)


# ── platform rules ──

def _set(db, rule_id, key, condition, *, severity, title, detail, now):
    if condition:
        raise_alert(db, rule_id=rule_id, dedupe_key=key, category="Platform", severity=severity,
                    title=title, detail=detail, now=now)
    else:
        clear_alert(db, key, now)


def evaluate_platform(db: Session, now: datetime) -> None:
    pending_count, oldest_pending = db.execute(select(func.count(), func.min(IngestedEvent.received_at)).where(
        IngestedEvent.process_status == "pending")).one()
    age_min = (now - oldest_pending).total_seconds() / 60 if oldest_pending else 0
    critical = age_min >= settings.monitor_backlog_critical_minutes or pending_count > settings.monitor_backlog_count_limit
    _set(db, "PL-01", "PL-01", age_min >= settings.monitor_backlog_warning_minutes or critical,
         severity="Critical" if critical else "Warning", now=now,
         title=f"Ingestion backlog: {pending_count} events, oldest {round(age_min)} min",
         detail={"pending": pending_count, "oldest_minutes": round(age_min, 1)})

    failed = db.execute(select(func.count()).where(
        IngestedEvent.process_status == "failed", IngestedEvent.received_at >= now - timedelta(hours=1))).scalar()
    _set(db, "PL-02", "PL-02", failed > settings.monitor_failed_events_per_hour, severity="Warning", now=now,
         title=f"Failed events: {failed} in the last hour", detail={"failed_last_hour": failed})

    last_processed = db.execute(select(func.max(IngestedEvent.processed_at))).scalar()
    stall = timedelta(minutes=settings.monitor_worker_stall_minutes)
    stalled = (pending_count > 0 and oldest_pending is not None and now - oldest_pending > stall
               and (last_processed is None or now - last_processed > stall))
    _set(db, "PL-03", "PL-03", stalled, severity="Critical", now=now,
         title="Ingestion worker not running: pending events are not being processed",
         detail={"pending": pending_count,
                 "last_processed_at": last_processed.isoformat() if last_processed else None})

    probe = checks.database_probe(db)
    _set(db, "PL-04", "PL-04", probe.get("ok") and probe["latency_ms"] > settings.monitor_db_slow_ms,
         severity="Warning", now=now, title=f"Database slow: {probe.get('latency_ms')} ms", detail=probe)

    disk = checks.disk_probe()
    free = disk.get("free_percent")
    _set(db, "PL-05", "PL-05", free is not None and free < 20, severity="Critical" if free is not None and free < 10 else "Warning",
         now=now, title=f"Database disk low: {free}% free", detail=disk)

    cert = checks.certificate_probe(now)
    days = cert.get("days_left")
    cert_problem = cert.get("configured") and (cert.get("error") or (days is not None and days <= 30))
    _set(db, "PL-06", "PL-06", cert_problem, now=now,
         severity="Critical" if (days is not None and days <= 7) or cert.get("error") else "Warning",
         title=(f"Certificate cannot be read: {cert.get('error')}" if cert.get("error")
                else f"Certificate expires in {days} days"), detail=cert)

    api = checks.api_errors.snapshot()
    _set(db, "PL-07", "PL-07", api["requests"] >= settings.monitor_api_error_min_requests
         and api["error_percent"] > settings.monitor_api_error_rate_percent, severity="Warning", now=now,
         title=f"API errors: {api['error_percent']}% of requests in 10 min", detail=api)

    backup = checks.backup_probe(now)
    age = backup.get("age_hours")
    _set(db, "PL-08", "PL-08", backup.get("configured") and (age is None or age > 24 or backup.get("error")),
         severity="Warning", now=now,
         title="No successful backup in 24 hours" if age is None or age > 24 else "Backup status unreadable",
         detail=backup)


# ── security rules ──

def evaluate_security(db: Session, now: datetime) -> None:
    """SE-01: a user with repeated failed logins in 15 minutes. (SE-02/03
    belong to the password-reset and break-glass features; SE-04 is raised
    when roles or approvers change.)"""
    since = now - timedelta(minutes=15)
    username = AuditLog.detail["username"].astext
    counts = dict(db.execute(select(username, func.count()).where(
        AuditLog.event_type.in_(("login_failure", "account_locked")), AuditLog.occurred_at >= since,
    ).group_by(username)).all())
    open_keys = {f"SE-01|{u}" for u, c in counts.items() if u and c >= settings.monitor_login_failure_limit}
    for key in open_keys:
        user = key.split("|", 1)[1]
        raise_alert(db, rule_id="SE-01", dedupe_key=key, category="Security", severity="Warning", now=now,
                    title=f"Repeated failed logins for '{user}': {counts[user]} in 15 min",
                    detail={"username": user, "failures_15_min": counts[user]})
    from app.models.monitoring import UsvAlert
    for alert in db.execute(select(UsvAlert).where(UsvAlert.rule_id == "SE-01", UsvAlert.status != "closed")).scalars():
        if alert.dedupe_key not in open_keys:
            clear_alert(db, alert.dedupe_key, now)


def run_monitoring(db: Session, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    limits = effective_settings(db)
    groups = [
        ("sites", lambda: evaluate_sites(db, now, limits)),
        ("rejected connections", lambda: evaluate_rejected_connections(db, now)),
        ("platform", lambda: evaluate_platform(db, now)),
        ("security", lambda: evaluate_security(db, now)),
        ("escalation", lambda: escalate_unacknowledged(db, lambda site_id: limits(site_id)["escalation_minutes"], now)),
        ("password resets", lambda: identity_flows.escalate_stale_resets(db, now)),
        ("break-glass rotation", lambda: identity_flows.rotate_due_break_glass(db, now)),
    ]
    db_key = db.get_bind().url.render_as_string(hide_password=True)
    if now - _last_volume_check.get(db_key, datetime.min.replace(tzinfo=timezone.utc)) >= VOLUME_CHECK_EVERY:
        _last_volume_check[db_key] = now
        groups.append(("volume", lambda: evaluate_volume(db, now)))
    for name, run in groups:
        try:
            run()
            db.commit()
        except Exception:  # noqa: BLE001 -- one rule group must not stop the others
            db.rollback()
            logger.exception("monitoring rule group '%s' failed", name)
