import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import get_current_user, get_db
from app.models.usv_user import UsvUser
from app.schemas.site import SiteResponse
from app.services.site_service import SiteService

router = APIRouter(prefix="/api/v1/site", tags=["site"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "SITE_NOT_FOUND", "message": "Site not found"}},
    )


@router.get("", response_model=list[SiteResponse])
def list_sites(
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[SiteResponse]:
    sites = SiteService(db).list_sites()
    return [SiteResponse.model_validate(site) for site in sites]


@router.get("/{site_id}", response_model=SiteResponse)
def get_site(
    site_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> SiteResponse:
    site = SiteService(db).get_site(site_id)
    if site is None:
        raise _not_found()
    return SiteResponse.model_validate(site)
