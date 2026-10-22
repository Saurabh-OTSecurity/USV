import uuid
from typing import Optional

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.rbac import (
    USV_BU_ADMIN, USV_CUSTOMER_ADMIN, USV_PLATFORM_ADMIN, USV_SITE_ADMIN, get_current_user, get_db, require_role,
)
from app.models.fleet_asset import FleetAsset
from app.services.access_scope import can_manage_site, visible_site_ids
from app.services.ingestion_worker import decommission_fleet_asset
from app.models.usv_user import UsvUser
from app.schemas.fleet import (
    AlertResponse,
    ConfirmDecommissionRequest,
    CorrelationGroupResponse,
    FleetAssetResponse,
    IncidentResponse,
    RemediationResponse,
    SiteHealthResponse,
    TombstoneResponse,
    TopologyLinkResponse,
)
from app.services.fleet_service import FleetService

router = APIRouter(prefix="/api/v1/fleet", tags=["fleet"])

# FR-3.1/Section 4.3: every list endpoint here takes the same filter
# convention -- ?siteId= (site-wise), ?businessUnitId= (BU-compiled), or
# neither (fully compiled/comprehensive across every site). Declared once as
# a dependency-free parameter block, shared by every route below, rather
# than each endpoint inventing its own filtering.
#
# Paging: with hundreds of sites the comprehensive view holds 100k+ assets,
# so every list takes ?limit= (default 500, max 5000) and ?offset=, and
# reports the full filtered count in the X-Total-Count response header. The
# body stays a plain JSON list, so existing callers keep working.
DEFAULT_PAGE_SIZE = 500
MAX_PAGE_SIZE = 5000


class Page:
    def __init__(
        self,
        limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
        offset: int = Query(0, ge=0),
    ):
        self.limit = limit
        self.offset = offset


def _with_total(response: Response, total: int) -> None:
    response.headers["X-Total-Count"] = str(total)


@router.get("/assets", response_model=list[FleetAssetResponse])
def list_fleet_assets(
    response: Response,
    siteId: Optional[uuid.UUID] = None,
    siteIds: Optional[str] = None,
    businessUnitId: Optional[uuid.UUID] = None,
    businessUnitIds: Optional[str] = None,
    lifecycleState: Optional[str] = Query(None, pattern="^(active|silent|missing_from_tribot)$"),
    page: Page = Depends(),
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[FleetAssetResponse]:
    assets, total = FleetService(db, visible_site_ids(db, current_user)).list_assets(
        site_id=siteId, site_ids=siteIds, business_unit_id=businessUnitId, business_unit_ids=businessUnitIds,
        limit=page.limit, offset=page.offset, lifecycle_state=lifecycleState,
    )
    _with_total(response, total)
    return [FleetAssetResponse.model_validate(a) for a in assets]


@router.get("/alerts", response_model=list[AlertResponse])
def list_fleet_alerts(
    response: Response,
    siteId: Optional[uuid.UUID] = None,
    siteIds: Optional[str] = None,
    businessUnitId: Optional[uuid.UUID] = None,
    businessUnitIds: Optional[str] = None,
    page: Page = Depends(),
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[AlertResponse]:
    alerts, total = FleetService(db, visible_site_ids(db, current_user)).list_alerts(
        site_id=siteId, site_ids=siteIds, business_unit_id=businessUnitId, business_unit_ids=businessUnitIds,
        limit=page.limit, offset=page.offset,
    )
    _with_total(response, total)
    return [AlertResponse.model_validate(a) for a in alerts]


@router.get("/remediations", response_model=list[RemediationResponse])
def list_fleet_remediations(
    response: Response,
    siteId: Optional[uuid.UUID] = None,
    siteIds: Optional[str] = None,
    businessUnitId: Optional[uuid.UUID] = None,
    businessUnitIds: Optional[str] = None,
    page: Page = Depends(),
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[RemediationResponse]:
    remediations, total = FleetService(db, visible_site_ids(db, current_user)).list_remediations(
        site_id=siteId, site_ids=siteIds, business_unit_id=businessUnitId, business_unit_ids=businessUnitIds,
        limit=page.limit, offset=page.offset,
    )
    _with_total(response, total)
    return [RemediationResponse.model_validate(r) for r in remediations]


@router.get("/incidents", response_model=list[IncidentResponse])
def list_fleet_incidents(
    response: Response,
    siteId: Optional[uuid.UUID] = None,
    siteIds: Optional[str] = None,
    businessUnitId: Optional[uuid.UUID] = None,
    businessUnitIds: Optional[str] = None,
    page: Page = Depends(),
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[IncidentResponse]:
    incidents, total = FleetService(db, visible_site_ids(db, current_user)).list_incidents(
        site_id=siteId, site_ids=siteIds, business_unit_id=businessUnitId, business_unit_ids=businessUnitIds,
        limit=page.limit, offset=page.offset,
    )
    _with_total(response, total)
    return [IncidentResponse.model_validate(i) for i in incidents]


@router.get("/correlation-groups", response_model=list[CorrelationGroupResponse])
def list_correlation_groups(
    acrossSitesOnly: bool = False,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[CorrelationGroupResponse]:
    """Related across sites (manual section 5): each group lists the sites
    its alerts come from, limited to the sites the caller may see.
    acrossSitesOnly keeps groups spanning two or more of those sites."""
    from app.models.alert import Alert

    visible = visible_site_ids(db, current_user)
    groups = FleetService(db, visible).list_correlation_groups()
    member_ids = {uuid.UUID(m) for g in groups for m in (g.member_ids or [])}
    site_of = dict(db.query(Alert.alert_id, Alert.site_id).filter(Alert.alert_id.in_(member_ids)).all())         if member_ids else {}
    out = []
    for g in groups:
        sites = sorted({str(site_of[uuid.UUID(m)]) for m in (g.member_ids or []) if uuid.UUID(m) in site_of
                        and (visible is None or site_of[uuid.UUID(m)] in visible)})
        if not sites or (acrossSitesOnly and len(sites) < 2):
            continue
        response = CorrelationGroupResponse.model_validate(g)
        response.site_ids = sites
        out.append(response)
    return out


@router.get("/topology-links", response_model=list[TopologyLinkResponse])
def list_fleet_topology_links(
    response: Response,
    siteId: Optional[uuid.UUID] = None,
    siteIds: Optional[str] = None,
    businessUnitId: Optional[uuid.UUID] = None,
    businessUnitIds: Optional[str] = None,
    page: Page = Depends(),
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[TopologyLinkResponse]:
    """Links pushed by each site's Tribot (who talks to whom), for the
    combined topology view (USV O&M Manual section 4). Endpoints are Tribot
    asset ids, matching fleet assets' source_asset_id within the same site."""
    links, total = FleetService(db, visible_site_ids(db, current_user)).list_topology_links(
        site_id=siteId, site_ids=siteIds, business_unit_id=businessUnitId, business_unit_ids=businessUnitIds,
        limit=page.limit, offset=page.offset,
    )
    _with_total(response, total)
    return [TopologyLinkResponse.model_validate(l) for l in links]


@router.get("/site-health", response_model=list[SiteHealthResponse])
def list_site_health(
    siteId: Optional[uuid.UUID] = None,
    siteIds: Optional[str] = None,
    businessUnitId: Optional[uuid.UUID] = None,
    businessUnitIds: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[SiteHealthResponse]:
    """The latest heartbeat health per site (manual section 7)."""
    rows = FleetService(db, visible_site_ids(db, current_user)).list_site_health(
        site_id=siteId, site_ids=siteIds, business_unit_id=businessUnitId, business_unit_ids=businessUnitIds,
    )
    return [SiteHealthResponse.model_validate(r) for r in rows]


@router.get("/decommissioned-assets", response_model=list[TombstoneResponse])
def list_decommissioned_assets(
    response: Response,
    siteId: Optional[uuid.UUID] = None,
    siteIds: Optional[str] = None,
    businessUnitId: Optional[uuid.UUID] = None,
    businessUnitIds: Optional[str] = None,
    page: Page = Depends(),
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[TombstoneResponse]:
    """Assets removed from the fleet (decommissioned in Tribot, or a
    missing-from-Tribot asset an admin confirmed), with who, when and why."""
    rows, total = FleetService(db, visible_site_ids(db, current_user)).list_tombstones(
        site_id=siteId, site_ids=siteIds, business_unit_id=businessUnitId, business_unit_ids=businessUnitIds,
        limit=page.limit, offset=page.offset,
    )
    _with_total(response, total)
    return [TombstoneResponse.model_validate(r) for r in rows]


def _missing_asset_or_404(db: Session, asset_id: uuid.UUID, user: UsvUser) -> FleetAsset:
    asset = db.get(FleetAsset, asset_id)
    if asset is None or not can_manage_site(db, user, asset.site_id):
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Asset not found"}})
    if asset.lifecycle_state != "missing_from_tribot":
        raise HTTPException(status_code=409, detail={"error": {
            "code": "NOT_MISSING", "message": "Only an asset marked missing from Tribot can be confirmed or dismissed"}})
    return asset


@router.post("/assets/{asset_id}/confirm-decommission", response_model=TombstoneResponse)
def confirm_missing_asset_decommission(
    asset_id: uuid.UUID,
    payload: ConfirmDecommissionRequest,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(require_role(USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN, USV_BU_ADMIN, USV_SITE_ADMIN)),
) -> TombstoneResponse:
    """An admin confirms that an asset the site's Tribot no longer lists is
    really gone (manual section 6 safety net): it is removed like a Tribot
    decommission, with the admin recorded in the audit entry."""
    asset = _missing_asset_or_404(db, asset_id, current_user)
    tombstone = decommission_fleet_asset(
        db, asset.tenant_id, asset.site_id, asset.source_asset_id, reason=payload.reason,
        decommissioned_by=current_user.username, decommissioned_at=datetime.now(timezone.utc),
        asset_name=asset.name, origin="usv_admin", actor_user_id=current_user.user_id,
    )
    db.commit()
    db.refresh(tombstone)
    return TombstoneResponse.model_validate(tombstone)


@router.post("/assets/{asset_id}/dismiss-missing", response_model=FleetAssetResponse)
def dismiss_missing_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(require_role(USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN, USV_BU_ADMIN, USV_SITE_ADMIN)),
) -> FleetAssetResponse:
    """The asset is not gone (e.g. the site's inventory was incomplete):
    clear the missing flag."""
    asset = _missing_asset_or_404(db, asset_id, current_user)
    asset.lifecycle_state = (asset.raw or {}).get("lifecycleState") or "active"
    db.commit()
    db.refresh(asset)
    return FleetAssetResponse.model_validate(asset)


@router.get("/site-summary")
def fleet_site_summary(
    siteIds: Optional[str] = None,
    businessUnitId: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[dict]:
    """One row per site with its counts (manual sections 4-5): assets
    (silent / missing from Tribot), open alerts by severity, open incidents
    and remediations, connection state and last contact. Grouped queries, so
    it stays cheap for hundreds of sites."""
    from sqlalchemy import func

    from app.models.alert import Alert
    from app.models.incident import Incident
    from app.models.monitoring import SiteState
    from app.models.remediation import Remediation
    from app.models.site import Site
    from app.services.fleet_scope import resolve_site_id_filter

    from app.services.ingestion_worker import CLOSED_ALERT_STATUSES

    requested = resolve_site_id_filter(db, site_ids=siteIds, business_unit_id=businessUnitId)
    visible = visible_site_ids(db, current_user)
    sites = [s for s in db.query(Site).all()
             if (requested is None or s.site_id in requested) and (visible is None or s.site_id in visible)]
    ids = [s.site_id for s in sites]
    if not ids:
        return []

    assets = {}
    for site_id, state, count in db.query(FleetAsset.site_id, FleetAsset.lifecycle_state, func.count()).filter(
            FleetAsset.site_id.in_(ids)).group_by(FleetAsset.site_id, FleetAsset.lifecycle_state):
        assets.setdefault(site_id, {})[state] = count
    alerts = {}
    for site_id, severity, count in db.query(Alert.site_id, func.lower(func.coalesce(Alert.severity, "unknown")),
                                             func.count()).filter(
            Alert.site_id.in_(ids), func.coalesce(Alert.status, "Open").notin_(CLOSED_ALERT_STATUSES)
    ).group_by(Alert.site_id, func.lower(func.coalesce(Alert.severity, "unknown"))):
        alerts.setdefault(site_id, {})[severity] = count
    closed = ("Closed", "Resolved", "Done", "Completed", "closed", "resolved", "done", "completed")
    incidents = dict(db.query(Incident.site_id, func.count()).filter(
        Incident.site_id.in_(ids), func.coalesce(Incident.status, "open").notin_(closed)).group_by(Incident.site_id).all())
    remediations = dict(db.query(Remediation.site_id, func.count()).filter(
        Remediation.site_id.in_(ids), func.coalesce(Remediation.status, "open").notin_(closed))
        .group_by(Remediation.site_id).all())
    states = {s.site_id: s for s in db.query(SiteState).filter(SiteState.site_id.in_(ids))}

    out = []
    for s in sites:
        a = assets.get(s.site_id, {})
        st = states.get(s.site_id)
        out.append({
            "site_id": str(s.site_id), "site_code": s.site_code, "name": s.name,
            "business_unit_id": str(s.business_unit_id),
            "assets": sum(a.values()), "silent_assets": a.get("silent", 0),
            "missing_assets": a.get("missing_from_tribot", 0),
            "open_alerts": alerts.get(s.site_id, {}),
            "open_incidents": incidents.get(s.site_id, 0), "open_remediations": remediations.get(s.site_id, 0),
            "state": st.state if st else "waiting_first_data",
            "last_contact_at": st.last_contact_at.isoformat() if st and st.last_contact_at else None,
        })
    return sorted(out, key=lambda r: r["site_code"])
