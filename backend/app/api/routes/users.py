import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.rbac import ALL_ROLES, USV_CUSTOMER_ADMIN, USV_PLATFORM_ADMIN, get_db, require_role
from app.models.business_unit import BusinessUnit
from app.models.site import Site
from app.models.usv_user import UsvUser
from app.schemas.usv_user import UserCreateRequest, UserProfile
from app.services.audit_service import AuditService
from app.services.monitoring.alerts import record_event
from app.services.user_service import UserService, UsernameAlreadyExistsError

router = APIRouter(prefix="/api/v1/users", tags=["users"])

# People are managed by platform admins, and by a customer admin within their
# own customer (USV O&M Manual section 11). Only a platform admin may create or
# grant the platform admin role.
USER_ADMINS = (USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN)


def _username_already_exists_error() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"error": {"code": "USERNAME_ALREADY_EXISTS", "message": "That username is already in use."}},
    )


def _check_grant(db: Session, actor: UsvUser, role: str, site_id: uuid.UUID | None,
                 business_unit_id: uuid.UUID | None) -> None:
    if role == USV_PLATFORM_ADMIN and actor.role != USV_PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail={"error": {
            "code": "FORBIDDEN", "message": "Only a platform admin can grant the platform admin role"}})
    if site_id is not None and db.get(Site, site_id) is None:
        raise HTTPException(status_code=422, detail={"error": {"code": "UNKNOWN_SITE", "message": "Unknown site_id"}})
    if business_unit_id is not None and db.get(BusinessUnit, business_unit_id) is None:
        raise HTTPException(status_code=422, detail={"error": {
            "code": "UNKNOWN_BUSINESS_UNIT", "message": "Unknown business_unit_id"}})


@router.get("", response_model=list[UserProfile])
def list_users(db: Session = Depends(get_db),
               current_user: UsvUser = Depends(require_role(*USER_ADMINS))) -> list[UserProfile]:
    users = UserService(db).list_users()
    return [UserProfile.model_validate(user) for user in users]


@router.post("", response_model=UserProfile)
def create_user(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(require_role(*USER_ADMINS)),
) -> UserProfile:
    _check_grant(db, current_user, payload.role, payload.site_id, payload.business_unit_id)
    try:
        user = UserService(db).create_user(
            username=payload.username,
            password=payload.password,
            role=payload.role,
            display_name=payload.display_name,
            site_id=payload.site_id,
            business_unit_id=payload.business_unit_id,
            actor_user_id=current_user.user_id,
        )
    except UsernameAlreadyExistsError:
        raise _username_already_exists_error()
    return UserProfile.model_validate(user)


class RoleChangeRequest(BaseModel):
    role: str
    site_id: uuid.UUID | None = None
    business_unit_id: uuid.UUID | None = None

    @field_validator("role")
    @classmethod
    def role_must_be_valid(cls, value: str) -> str:
        if value not in ALL_ROLES:
            raise ValueError(f"role must be one of {ALL_ROLES}")
        return value


@router.put("/{user_id}/role", response_model=UserProfile)
def change_role(
    user_id: uuid.UUID,
    payload: RoleChangeRequest,
    db: Session = Depends(get_db),
    current_user: UsvUser = Depends(require_role(*USER_ADMINS)),
) -> UserProfile:
    """Changes a person's role and where it applies (site or business unit).
    Raises the SE-04 "role or approver changed" event and an audit entry."""
    user = db.get(UsvUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found"}})
    if user.role == USV_PLATFORM_ADMIN and current_user.role != USV_PLATFORM_ADMIN:
        raise HTTPException(status_code=403, detail={"error": {
            "code": "FORBIDDEN", "message": "Only a platform admin can change a platform admin"}})
    _check_grant(db, current_user, payload.role, payload.site_id, payload.business_unit_id)

    before = {"role": user.role, "site_id": str(user.site_id) if user.site_id else None,
              "business_unit_id": str(user.business_unit_id) if user.business_unit_id else None}
    user.role, user.site_id, user.business_unit_id = payload.role, payload.site_id, payload.business_unit_id
    after = {"role": user.role, "site_id": str(user.site_id) if user.site_id else None,
             "business_unit_id": str(user.business_unit_id) if user.business_unit_id else None}
    record_event(db, rule_id="SE-04", category="Security", site_id=user.site_id,
                 title=f"Role changed for {user.username}: {before['role']} -> {after['role']}",
                 detail={"username": user.username, "before": before, "after": after,
                         "changed_by": current_user.username})
    db.commit()
    AuditService(db).record(event_type="user_role_changed", actor_user_id=current_user.user_id,
                            target_type="usv_user", target_id=user.user_id, result="success",
                            detail={"before": before, "after": after})
    db.refresh(user)
    return UserProfile.model_validate(user)
