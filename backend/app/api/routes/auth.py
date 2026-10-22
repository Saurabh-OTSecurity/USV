from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rbac import get_current_user, get_db
from app.core.tenancy import MULTI_TENANT_POOL, resolve_tenant_database_name_by_code, session_for_tenant
from app.models.usv_user import UsvUser
from app.schemas.usv_user import LoginRequest, LoginResponse, UserProfile
from app.services.auth_service import AuthService, InvalidCredentialsError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _invalid_credentials_error() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid username or password"}},
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    tenant_id = None
    session = db
    owns_session = False

    if settings.deployment_mode == MULTI_TENANT_POOL and payload.tenant_code:
        tenant_id, database_name = resolve_tenant_database_name_by_code(payload.tenant_code)
        session = session_for_tenant(tenant_id)
        owns_session = True

    try:
        service = AuthService(session)
        try:
            token, user = service.login(payload.username, payload.password, _client_ip(request), tenant_id=tenant_id)
        except InvalidCredentialsError:
            raise _invalid_credentials_error()

        return LoginResponse(token=token, user=UserProfile.model_validate(user))
    finally:
        if owns_session:
            session.close()


@router.get("/me", response_model=UserProfile)
def me(current_user: UsvUser = Depends(get_current_user)) -> UserProfile:
    return UserProfile.model_validate(current_user)


@router.post("/logout")
def logout(current_user: UsvUser = Depends(get_current_user)) -> dict:
    return {"message": "Logged out. This is a client-side token discard only; the token remains valid until it expires."}
