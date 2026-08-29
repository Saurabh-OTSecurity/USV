import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.usv_user import UsvUser
from app.repositories.usv_user_repository import UsvUserRepository
from app.services.audit_service import AuditService


class UsernameAlreadyExistsError(Exception):
    pass


class UserService:
    def __init__(self, db: Session):
        self.repository = UsvUserRepository(db)
        self.audit = AuditService(db)

    def list_users(self) -> list[UsvUser]:
        return self.repository.list_all()

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str,
        display_name: str | None,
        site_id: uuid.UUID | None,
        actor_user_id: uuid.UUID,
    ) -> UsvUser:
        user = UsvUser(
            username=username,
            password_hash=hash_password(password),
            role=role,
            display_name=display_name,
            site_id=site_id,
        )
        try:
            user = self.repository.create(user)
        except IntegrityError:
            self.repository.db.rollback()
            raise UsernameAlreadyExistsError() from None

        self.audit.record(
            event_type="user_created",
            actor_user_id=actor_user_id,
            target_type="usv_user",
            target_id=user.user_id,
            result="success",
        )
        return user
