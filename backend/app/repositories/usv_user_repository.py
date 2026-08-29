import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.usv_user import UsvUser


class UsvUserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_username(self, username: str) -> UsvUser | None:
        return self.db.query(UsvUser).filter_by(username=username).one_or_none()

    def get_by_id(self, user_id: uuid.UUID) -> UsvUser | None:
        return self.db.get(UsvUser, user_id)

    def mark_login(self, user: UsvUser) -> UsvUser:
        user.last_login_at = datetime.now(timezone.utc)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def list_all(self) -> list[UsvUser]:
        return self.db.query(UsvUser).order_by(UsvUser.username).all()

    def create(self, user: UsvUser) -> UsvUser:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
