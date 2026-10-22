import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import USV_CUSTOMER_ADMIN, USV_PLATFORM_ADMIN, get_current_user, get_db, require_role
from app.models.site import Site
from app.services.access_scope import visible_site_ids
from app.models.usv_user import UsvUser
from app.schemas.business_unit import BusinessUnitCreate, BusinessUnitResponse
from app.services.business_unit_service import BusinessUnitService

router = APIRouter(prefix="/api/v1/business-units", tags=["business-units"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "BUSINESS_UNIT_NOT_FOUND", "message": "Business unit not found"}},
    )


@router.get("", response_model=list[BusinessUnitResponse])
def list_business_units(
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[BusinessUnitResponse]:
    units = BusinessUnitService(db).list_business_units()
    visible = visible_site_ids(db, current_user)
    if visible is not None:
        # a BU is visible when the caller can see at least one of its sites
        # (or it is the BU admin's own BU, even before it has sites)
        bu_ids = {s.business_unit_id for s in db.query(Site).filter(Site.site_id.in_(visible))}
        if current_user.business_unit_id:
            bu_ids.add(current_user.business_unit_id)
        units = [u for u in units if u.business_unit_id in bu_ids]
    return [BusinessUnitResponse.model_validate(unit) for unit in units]


@router.get("/{business_unit_id}", response_model=BusinessUnitResponse)
def get_business_unit(
    business_unit_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> BusinessUnitResponse:
    unit = BusinessUnitService(db).get_business_unit(business_unit_id)
    if unit is None:
        raise _not_found()
    return BusinessUnitResponse.model_validate(unit)


@router.post("", response_model=BusinessUnitResponse, status_code=201)
def create_business_unit(
    payload: BusinessUnitCreate,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(require_role(USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN)),
) -> BusinessUnitResponse:
    """Business units are set up by a customer admin (USV O&M Manual section 11)."""
    unit = BusinessUnitService(db).create_business_unit(payload.name)
    return BusinessUnitResponse.model_validate(unit)
