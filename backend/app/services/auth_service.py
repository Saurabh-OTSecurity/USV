import uuid

from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.tenant import Tenant
from app.models.usv_user import UsvUser
from app.repositories.usv_user_repository import UsvUserRepository
from app.services.audit_service import AuditService
from app.services.password_policy import is_expired, register_failed_login


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UsvUserRepository(db)
        self.audit = AuditService(db)

    def login(
        self,
        username: str,
        password: str,
        source_ip: str | None,
        tenant_id: uuid.UUID | None = None,
    ) -> tuple[str, UsvUser]:
        user = self.users.get_by_username(username)

        # A locked account is refused even with the right password (USV O&M
        # Manual section 10: 5 failed logins lock it; an admin unlocks).
        password_ok = user is not None and verify_password(password, user.password_hash)
        if user is None or not password_ok or user.status != "active" or user.locked_at is not None:
            detail = {"username": username}
            if user is not None and user.locked_at is not None:
                detail["reason"] = "locked"
            elif user is not None and not password_ok and register_failed_login(self.db, user):
                self.db.commit()
                self.audit.record(event_type="account_locked", actor_user_id=user.user_id, result="failure",
                                  source_ip=source_ip, detail={"username": username})
            elif user is not None:
                self.db.commit()
            self.audit.record(
                event_type="login_failure",
                actor_user_id=user.user_id if user is not None else None,
                result="failure",
                source_ip=source_ip,
                detail=detail,
            )
            raise InvalidCredentialsError()

        if user.failed_login_count:
            user.failed_login_count = 0
        if is_expired(self.db, user):
            user.must_change_password = True

        user = self.users.mark_login(user)

        # SINGLE_TENANT mode: tenant_id isn't passed by the caller (there's
        # no login-time tenant selection), so opportunistically pick up the
        # one Tenant row this database has, if T-1's migration has run.
        # MULTI_TENANT_POOL mode: the auth route already resolved tenant_id
        # from the login request's tenant_code before calling this.
        resolved_tenant_id = tenant_id
        if resolved_tenant_id is None:
            tenant = self.db.query(Tenant).first()
            resolved_tenant_id = tenant.tenant_id if tenant is not None else None

        token = create_access_token(
            user_id=str(user.user_id),
            role=user.role,
            site_id=str(user.site_id) if user.site_id is not None else None,
            tenant_id=str(resolved_tenant_id) if resolved_tenant_id is not None else None,
            business_unit_id=str(user.business_unit_id) if user.business_unit_id is not None else None,
            tenant_db=tenant_id is not None,
        )

        self.audit.record(
            event_type="login_success",
            actor_user_id=user.user_id,
            result="success",
            source_ip=source_ip,
        )

        return token, user
