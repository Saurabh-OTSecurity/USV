import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import USV_BU_ADMIN, USV_CUSTOMER_ADMIN, USV_PLATFORM_ADMIN, get_current_user, get_db, require_role
from app.services.access_scope import can_manage_business_unit, can_manage_site, can_view_site, visible_site_ids
from app.models.usv_user import UsvUser
from app.schemas.site import SiteCreate, SiteResponse, SiteTribotUrl
from app.services.monitoring import rules as monitoring_rules
from app.services.site_service import SiteCodeAlreadyExistsError, SiteService

router = APIRouter(prefix="/api/v1/site", tags=["site"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "SITE_NOT_FOUND", "message": "Site not found"}},
    )


def _site_code_conflict() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"error": {"code": "SITE_CODE_EXISTS", "message": "A site with this site_code already exists"}},
    )


@router.get("", response_model=list[SiteResponse])
def list_sites(
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[SiteResponse]:
    visible = visible_site_ids(db, current_user)
    sites = SiteService(db).list_sites()
    return [SiteResponse.model_validate(site) for site in sites if visible is None or site.site_id in visible]


@router.get("/{site_id}", response_model=SiteResponse)
def get_site(
    site_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> SiteResponse:
    site = SiteService(db).get_site(site_id)
    if site is None or not can_view_site(db, current_user, site_id):
        raise _not_found()
    return SiteResponse.model_validate(site)


@router.post("", response_model=SiteResponse, status_code=201)
def create_site(
    payload: SiteCreate,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(require_role(USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN, USV_BU_ADMIN)),
) -> SiteResponse:
    """Register a new site -- e.g. a second physical/OT location running its
    own Tribot instance. This only creates the Site + Business Unit
    assignment; to actually receive that site's Tribot data, also issue it
    an ingestion credential (POST /api/v1/sites/{site_id}/ingestion-tokens,
    see app/api/routes/ingestion_tokens.py) and point that Tribot instance's
    usv_push config at this ECC's POST /api/v1/ingest/tribot endpoint with
    that credential.

    Sites are set up by a customer admin, or by a BU admin within their own
    business unit (USV O&M Manual section 11)."""
    if not can_manage_business_unit(current_user, payload.business_unit_id):
        raise HTTPException(status_code=403, detail={"error": {
            "code": "FORBIDDEN", "message": "You can only add sites to your own business unit"}})
    try:
        site = SiteService(db).create_site(
            site_code=payload.site_code,
            name=payload.name,
            business_unit_id=payload.business_unit_id,
            description=payload.description,
            timezone=payload.timezone,
            criticality=payload.criticality,
            tribot_url=payload.tribot_url,
        )
    except SiteCodeAlreadyExistsError:
        raise _site_code_conflict()
    monitoring_rules.site_added(db, site)
    db.commit()
    return SiteResponse.model_validate(site)


@router.put("/{site_id}/tribot-url", response_model=SiteResponse)
def set_tribot_url(
    site_id: uuid.UUID,
    payload: SiteTribotUrl,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> SiteResponse:
    """Where people open this site's Tribot; USV sends single-sign-on users there."""
    site = SiteService(db).get_site(site_id)
    if site is None or not can_manage_site(db, current_user, site_id):
        raise _not_found()
    site.tribot_url = payload.tribot_url
    db.commit()
    db.refresh(site)
    return SiteResponse.model_validate(site)
