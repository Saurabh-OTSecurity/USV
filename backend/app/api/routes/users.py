from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.rbac import USV_PLATFORM_ADMIN, get_db, require_role
from app.models.usv_user import UsvUser
from app.schemas.usv_user import UserCreateRequest, UserProfile
from app.services.user_service import UserService, UsernameAlreadyExistsError

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _username_already_exists_error() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"error": {"code": "USERNAME_ALREADY_EXISTS", "message": "That username is already in use."}},
    )


@router.get("", response_model=list[UserProfile], dependencies=[Depends(require_role(USV_PLATFORM_ADMIN))])
def list_users(db: Session = Depends(get_db)) -> list[UserProfile]:
    users = UserService(db).list_users()
    return [UserProfile.model_validate(user) for user in users]


@router.post("", response_model=UserProfile, dependencies=[Depends(require_role(USV_PLATFORM_ADMIN))])
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(require_role(USV_PLATFORM_ADMIN)),
) -> UserProfile:
    try:
        user = UserService(db).create_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
            display_name=payload.display_name,
            site_id=payload.site_id,
            actor_user_id=current_user.user_id,
        )
    except UsernameAlreadyExistsError:
        raise _username_already_exists_error()
    return UserProfile.model_validate(user)
