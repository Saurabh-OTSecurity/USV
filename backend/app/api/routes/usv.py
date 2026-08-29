import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import get_current_user, get_db
from app.models.usv_user import UsvUser
from app.schemas.usv import UsvResponse
from app.services.usv_service import UsvService

router = APIRouter(prefix="/api/v1/usv", tags=["usv"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "USV_NOT_FOUND", "message": "USV not found"}},
    )


@router.get("", response_model=list[UsvResponse])
def list_usvs(
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> list[UsvResponse]:
    usvs = UsvService(db).list_usvs()
    return [UsvResponse.model_validate(usv) for usv in usvs]


@router.get("/{usv_id}", response_model=UsvResponse)
def get_usv(
    usv_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(get_current_user),
) -> UsvResponse:
    usv = UsvService(db).get_usv(usv_id)
    if usv is None:
        raise _not_found()
    return UsvResponse.model_validate(usv)
