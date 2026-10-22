"""FR-3.6: group alerts (and, later, incidents) sharing a CVE across sites
within a tenant -- keyed by CVE plus the affected asset's type (USV O&M
Manual section 9 decision), so the same CVE on PLCs and on workstations are
separate findings with separate fixes. On-write (called from the ingestion worker as each alert is
normalized) rather than a scheduled job -- simplest correct option for
current data volume; revisit if alert rate makes on-write grouping a
bottleneck. Deliberately does not re-run Tribot's detection logic (FR-3.7)
-- correlation only ever groups on already-reported fields (here: cve_id).
"""
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.correlation_group import CorrelationGroup
from app.models.fleet_asset import FleetAsset


def asset_type_for(db: Session, alert: Alert) -> str:
    """The linked fleet asset's device type, else what the alert itself
    says, else "unknown"."""
    if alert.asset_id is not None:
        asset = db.get(FleetAsset, alert.asset_id)
        if asset is not None and asset.device_type:
            return asset.device_type
    raw = alert.raw or {}
    return raw.get("deviceType") or raw.get("assetType") or "unknown"


def correlate_alert(db: Session, alert: Alert) -> CorrelationGroup | None:
    if not alert.cve_id:
        return None

    asset_type = asset_type_for(db, alert)
    correlation_key = f"cve:{alert.cve_id}|type:{asset_type.lower()}"
    group = (
        db.query(CorrelationGroup)
        .filter_by(tenant_id=alert.tenant_id, correlation_key=correlation_key)
        .one_or_none()
    )
    if group is None:
        group = CorrelationGroup(
            tenant_id=alert.tenant_id,
            correlation_key=correlation_key,
            title=f"{alert.cve_id} on {asset_type} assets",
            member_type="alert",
            member_ids=[],
        )
        db.add(group)
        db.flush()

    member_ids = list(group.member_ids or [])
    alert_id_str = str(alert.alert_id)
    if alert_id_str not in member_ids:
        member_ids.append(alert_id_str)
        group.member_ids = member_ids

    return group
