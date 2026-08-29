from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.rbac import get_current_user, get_db
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
    service = AuthService(db)
    try:
        token, user = service.login(payload.username, payload.password, _client_ip(request))
    except InvalidCredentialsError:
        raise _invalid_credentials_error()

    return LoginResponse(token=token, user=UserProfile.model_validate(user))


@router.get("/me", response_model=UserProfile)
def me(current_user: UsvUser = Depends(get_current_user)) -> UserProfile:
    return UserProfile.model_validate(current_user)


@router.post("/logout")
def logout(current_user: UsvUser = Depends(get_current_user)) -> dict:
    return {"message": "Logged out. This is a client-side token discard only; the token remains valid until it expires."}
