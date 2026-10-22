"""Customers on a shared USV (MULTI_TENANT_POOL: one database per customer).

Tribastion platform admins -- users of the platform database, not of any
customer database -- list and add customers here. Adding a customer creates
its database, runs every migration on it, seeds its tenant row and default
business unit, and creates its first customer admin, whose one-time password
is shown once in the response (in-app only; the person must be told it
through a separate channel).
"""
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.core.rbac import USV_CUSTOMER_ADMIN, USV_PLATFORM_ADMIN, require_role
from app.core.security import hash_password
from app.core.tenancy import MULTI_TENANT_POOL, platform_session, session_for_tenant, tenant_id_from_authorization
from app.models.audit_log import AuditLog
from app.models.tenant_registry import TenantRegistry
from app.models.usv_user import UsvUser
from app.services.tenant_provisioning_service import provision_tenant

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


def _require_platform_level(request: Request) -> None:
    if settings.deployment_mode != MULTI_TENANT_POOL:
        raise HTTPException(status_code=409, detail={"error": {
            "code": "SINGLE_TENANT", "message": "This USV runs in single-customer mode (DEPLOYMENT_MODE)"}})
    if tenant_id_from_authorization(request.headers.get("authorization")) is not None:
        raise HTTPException(status_code=403, detail={"error": {
            "code": "FORBIDDEN", "message": "Customers are managed by Tribastion platform admins only"}})


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: object
    tenant_code: str
    name: str
    database_name: str
    status: str


class CustomerCreate(BaseModel):
    tenant_code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=255)
    admin_username: str = Field(min_length=3, max_length=128)
    admin_display_name: str | None = None

    @field_validator("tenant_code")
    @classmethod
    def _code(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
            raise ValueError("tenant_code may contain letters, digits, '-' and '_'")
        return value.upper()


class CustomerCreated(CustomerResponse):
    admin_username: str
    # Shown once. Hand it to the customer admin through a separate channel;
    # they should change it at first login.
    admin_one_time_password: str


@router.get("/customers", response_model=list[CustomerResponse])
def list_customers(request: Request,
                   current_user: UsvUser = Depends(require_role(USV_PLATFORM_ADMIN))) -> list[CustomerResponse]:
    _require_platform_level(request)
    with platform_session() as db:
        return [CustomerResponse.model_validate(t) for t in
                db.query(TenantRegistry).order_by(TenantRegistry.tenant_code).all()]


@router.post("/customers", response_model=CustomerCreated, status_code=201)
def create_customer(payload: CustomerCreate, request: Request,
                    current_user: UsvUser = Depends(require_role(USV_PLATFORM_ADMIN))) -> CustomerCreated:
    _require_platform_level(request)
    with platform_session() as db:
        if db.query(TenantRegistry).filter_by(tenant_code=payload.tenant_code, status="ready").first():
            raise HTTPException(status_code=409, detail={"error": {
                "code": "CUSTOMER_EXISTS", "message": "A customer with this tenant_code already exists"}})

    entry = provision_tenant(payload.tenant_code, payload.name)

    password = secrets.token_urlsafe(12)
    tenant_db = session_for_tenant(entry.tenant_id)
    try:
        if tenant_db.query(UsvUser).filter_by(username=payload.admin_username).first() is None:
            tenant_db.add(UsvUser(username=payload.admin_username, password_hash=hash_password(password),
                                  role=USV_CUSTOMER_ADMIN, display_name=payload.admin_display_name))
            tenant_db.commit()
        else:
            raise HTTPException(status_code=409, detail={"error": {
                "code": "USERNAME_ALREADY_EXISTS", "message": "That admin username already exists for this customer"}})
    finally:
        tenant_db.close()

    with platform_session() as db:
        db.add(AuditLog(occurred_at=datetime.now(timezone.utc), event_type="customer_provisioned",
                        actor_user_id=current_user.user_id, target_type="tenant", target_id=entry.tenant_id,
                        result="success", detail={"tenant_code": entry.tenant_code, "name": entry.name,
                                                  "admin_username": payload.admin_username}))
        db.commit()

    return CustomerCreated(tenant_id=entry.tenant_id, tenant_code=entry.tenant_code, name=entry.name,
                           database_name=entry.database_name, status=entry.status,
                           admin_username=payload.admin_username, admin_one_time_password=password)
