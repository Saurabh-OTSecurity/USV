from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.usv_user import UsvUser
from app.repositories.usv_user_repository import UsvUserRepository
from app.services.audit_service import AuditService


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(self, db: Session):
        self.users = UsvUserRepository(db)
        self.audit = AuditService(db)

    def login(self, username: str, password: str, source_ip: str | None) -> tuple[str, UsvUser]:
        user = self.users.get_by_username(username)

        if user is None or not verify_password(password, user.password_hash) or user.status != "active":
            self.audit.record(
                event_type="login_failure",
                actor_user_id=user.user_id if user is not None else None,
                result="failure",
                source_ip=source_ip,
                detail={"username": username},
            )
            raise InvalidCredentialsError()

        user = self.users.mark_login(user)

        token = create_access_token(
            user_id=str(user.user_id),
            role=user.role,
            site_id=str(user.site_id) if user.site_id is not None else None,
        )

        self.audit.record(
            event_type="login_success",
            actor_user_id=user.user_id,
            result="success",
            source_ip=source_ip,
        )

        return token, user
