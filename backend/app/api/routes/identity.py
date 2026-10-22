"""Identity governance API (USV O&M Manual sections 10-11): password change,
unlock/disable, one-time secure shares, approvers, approved password resets,
break-glass. Unauthenticated endpoints (forgot password, opening a share)
take an optional tenant_code to reach the customer's database in
MULTI_TENANT_POOL mode, like login does."""
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.rbac import (
    USV_AUDITOR, USV_BU_ADMIN, USV_CUSTOMER_ADMIN, USV_L1_OPERATOR, USV_L2_ANALYST, USV_PLATFORM_ADMIN,
    USV_SITE_ADMIN, USV_VIEWER, get_current_user, get_db, require_role,
)
from app.core.tenancy import MULTI_TENANT_POOL, resolve_tenant_database_name_by_code, session_for_tenant
from app.models.identity import Approver, BreakGlassRequest
from app.models.site import Site
from app.models.usv_user import UsvUser
from app.services import identity_flows as flows
from app.services.access_scope import (
    CUSTOMER_ADMIN_ROLES, assigned_site_ids, bu_site_ids, can_manage_business_unit, can_manage_site,
)
from app.services.monitoring.alerts import record_event
from app.services.audit_service import AuditService
from app.services.password_policy import end_sessions, get_policy, set_password, validate_new_password

router = APIRouter(prefix="/api/v1", tags=["identity"])

ADMINS = (USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN, USV_BU_ADMIN, USV_SITE_ADMIN)


def _error(e: flows.FlowError) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"error": {"code": e.code, "message": e.message}})


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@contextmanager
def _public_session(tenant_code: str | None):
    if settings.deployment_mode == MULTI_TENANT_POOL and tenant_code:
        tenant_id, _ = resolve_tenant_database_name_by_code(tenant_code)
        db = session_for_tenant(tenant_id)
    else:
        db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


SITE_LEVEL_ROLES = {USV_L1_OPERATOR, USV_L2_ANALYST, USV_VIEWER, USV_AUDITOR}


def _can_administer_user(db: Session, admin: UsvUser, target: UsvUser) -> bool:
    """Who may unlock, disable or issue a password for whom -- always
    someone above the person, never themselves (manual section 11):
    platform admins anyone; a customer admin anyone but platform admins;
    a BU admin site admins and site people within their BU; a site admin
    the engineers and viewers of their own sites."""
    if target.user_id == admin.user_id:
        return False
    if admin.role == USV_PLATFORM_ADMIN:
        return True
    if target.role == USV_PLATFORM_ADMIN:
        return False
    if admin.role == USV_CUSTOMER_ADMIN:
        return True
    target_sites = assigned_site_ids(db, target)
    if admin.role == USV_BU_ADMIN:
        if target.role not in SITE_LEVEL_ROLES | {USV_SITE_ADMIN}:
            return False
        bu_sites = bu_site_ids(db, admin.business_unit_id)
        return bool(target_sites) and target_sites <= bu_sites
    if admin.role == USV_SITE_ADMIN:
        return target.role in SITE_LEVEL_ROLES and bool(target_sites) and target_sites <= assigned_site_ids(db, admin)
    return False


def _target(db: Session, admin: UsvUser, user_id: uuid.UUID) -> UsvUser:
    target = db.get(UsvUser, user_id)
    if target is None or not _can_administer_user(db, admin, target):
        raise HTTPException(status_code=404, detail={"error": {"code": "USER_NOT_FOUND", "message": "User not found"}})
    return target


# ── own password ──

class ChangePassword(BaseModel):
    current_password: str
    new_password: str


@router.post("/auth/change-password")
def change_password(payload: ChangePassword, db: Session = Depends(get_db),
                    current_user: UsvUser = Depends(get_current_user)) -> dict:
    from app.core.security import verify_password
    if not verify_password(payload.current_password, current_user.password_hash):
        # 400, not 401: the session itself is fine, and the UI signs people out on 401
        raise HTTPException(status_code=400, detail={"error": {"code": "WRONG_PASSWORD", "message": "Current password is wrong"}})
    problems = validate_new_password(db, current_user, payload.new_password)
    if problems:
        raise HTTPException(status_code=422, detail={"error": {"code": "PASSWORD_POLICY", "message": "; ".join(problems)}})
    set_password(db, current_user, payload.new_password)
    db.commit()
    AuditService(db).record(event_type="password_changed", actor_user_id=current_user.user_id, result="success")
    return {"message": "Password changed. Sign in again with the new password."}


@router.get("/auth/password-policy")
def password_policy(db: Session = Depends(get_db), current_user: UsvUser = Depends(get_current_user)) -> dict:
    p = get_policy(db)
    db.commit()
    return {"min_length": p.min_length, "history_count": p.history_count, "max_failed_logins": p.max_failed_logins,
            "expiry_days": p.expiry_days, "share_link_hours": p.share_link_hours,
            "reset_link_minutes": p.reset_link_minutes, "reset_approval_hours": p.reset_approval_hours}


# ── administering people ──

@router.post("/users/{user_id}/unlock")
def unlock_user(user_id: uuid.UUID, db: Session = Depends(get_db),
                current_user: UsvUser = Depends(require_role(*ADMINS))) -> dict:
    target = _target(db, current_user, user_id)
    target.locked_at, target.failed_login_count = None, 0
    db.commit()
    AuditService(db).record(event_type="user_unlocked", actor_user_id=current_user.user_id, target_type="usv_user",
                            target_id=target.user_id, result="success")
    return {"username": target.username, "locked": False}


@router.post("/users/{user_id}/disable")
def disable_user(user_id: uuid.UUID, db: Session = Depends(get_db),
                 current_user: UsvUser = Depends(require_role(*ADMINS))) -> dict:
    """The person left: they can't sign in anywhere, their USV sessions end
    now, and every Tribot drops them at its next directory poll."""
    target = _target(db, current_user, user_id)
    target.status = "disabled"
    end_sessions(target)
    db.commit()
    AuditService(db).record(event_type="user_disabled", actor_user_id=current_user.user_id, target_type="usv_user",
                            target_id=target.user_id, result="success")
    return {"username": target.username, "status": "disabled"}


@router.post("/users/{user_id}/enable")
def enable_user(user_id: uuid.UUID, db: Session = Depends(get_db),
                current_user: UsvUser = Depends(require_role(*ADMINS))) -> dict:
    target = _target(db, current_user, user_id)
    target.status = "active"
    db.commit()
    AuditService(db).record(event_type="user_enabled", actor_user_id=current_user.user_id, target_type="usv_user",
                            target_id=target.user_id, result="success")
    return {"username": target.username, "status": "active"}


@router.post("/users/{user_id}/initial-password-share")
def initial_password_share(user_id: uuid.UUID, db: Session = Depends(get_db),
                           current_user: UsvUser = Depends(require_role(*ADMINS))) -> dict:
    """Issues the person a temporary password behind a one-time link. The
    admin gets the link, never the password, and passes the link to the
    person through a separate channel; the person must set their own
    password at first login."""
    target = _target(db, current_user, user_id)
    token, expires = flows.create_initial_password_share(db, current_user, target)
    db.commit()
    return {"share_path": f"/share/{token}", "share_token": token, "expires_at": expires.isoformat(),
            "username": target.username}


# ── secure shares (no login: possession of the one-time link is the credential) ──

class ShareOpen(BaseModel):
    tenant_code: str | None = None


@router.post("/secure-shares/{token}/open")
def open_secure_share(token: str, request: Request, payload: ShareOpen | None = None) -> dict:
    with _public_session(payload.tenant_code if payload else None) as db:
        try:
            return flows.open_share(db, token, _ip(request))
        except flows.FlowError as e:
            raise _error(e)


# ── approvers ──

class ApproverCreate(BaseModel):
    level: str = Field(pattern="^(platform|customer|business_unit|site)$")
    scope_id: uuid.UUID | None = None
    user_id: uuid.UUID
    is_backup: bool = False


class ApproverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    approver_id: uuid.UUID
    level: str
    scope_id: uuid.UUID | None
    user_id: uuid.UUID
    is_backup: bool


def _can_set_approver(db: Session, admin: UsvUser, level: str, scope_id: uuid.UUID | None) -> bool:
    """Approvers are named one level above where they apply: platform admins
    name platform and customer approvers, customer admins BU approvers (and
    their own customer's), BU admins site approvers in their BU."""
    if level == "platform":
        return admin.role == USV_PLATFORM_ADMIN
    if level == "customer":
        return admin.role in CUSTOMER_ADMIN_ROLES
    if level == "business_unit":
        return scope_id is not None and admin.role in CUSTOMER_ADMIN_ROLES
    site = db.get(Site, scope_id) if scope_id else None
    return site is not None and can_manage_business_unit(admin, site.business_unit_id)


@router.get("/approvers", response_model=list[ApproverResponse])
def list_approvers(db: Session = Depends(get_db), current_user: UsvUser = Depends(require_role(*ADMINS))):
    return [ApproverResponse.model_validate(a) for a in db.execute(select(Approver)).scalars()]


@router.post("/approvers", response_model=ApproverResponse, status_code=201)
def add_approver(payload: ApproverCreate, db: Session = Depends(get_db),
                 current_user: UsvUser = Depends(require_role(*ADMINS))):
    if payload.level in ("business_unit", "site") and payload.scope_id is None:
        raise HTTPException(status_code=422, detail={"error": {"code": "SCOPE_REQUIRED", "message": "scope_id is required"}})
    if not _can_set_approver(db, current_user, payload.level, payload.scope_id):
        raise HTTPException(status_code=403, detail={"error": {"code": "FORBIDDEN", "message": "Not allowed at this level"}})
    if db.get(UsvUser, payload.user_id) is None:
        raise HTTPException(status_code=422, detail={"error": {"code": "UNKNOWN_USER", "message": "Unknown user"}})
    approver = Approver(level=payload.level, scope_id=payload.scope_id if payload.level in ("business_unit", "site") else None,
                        user_id=payload.user_id, is_backup=payload.is_backup)
    db.add(approver)
    record_event(db, rule_id="SE-04", category="Security", title=f"Approver added at {payload.level} level",
                 detail={"level": payload.level, "scope_id": str(payload.scope_id) if payload.scope_id else None,
                         "user_id": str(payload.user_id), "is_backup": payload.is_backup,
                         "changed_by": current_user.username})
    db.commit()
    db.refresh(approver)
    return ApproverResponse.model_validate(approver)


@router.delete("/approvers/{approver_id}", status_code=204)
def remove_approver(approver_id: uuid.UUID, db: Session = Depends(get_db),
                    current_user: UsvUser = Depends(require_role(*ADMINS))):
    approver = db.get(Approver, approver_id)
    if approver is None or not _can_set_approver(db, current_user, approver.level, approver.scope_id):
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Approver not found"}})
    db.delete(approver)
    record_event(db, rule_id="SE-04", category="Security", title=f"Approver removed at {approver.level} level",
                 detail={"approver_id": str(approver_id), "changed_by": current_user.username})
    db.commit()
    return Response(status_code=204)


# ── forgot password (approved reset) ──

class ResetRequest(BaseModel):
    username: str
    tenant_code: str | None = None


class ResetReference(BaseModel):
    reference: str
    tenant_code: str | None = None


class ResetComplete(ResetReference):
    new_password: str


@router.post("/password-resets")
def request_password_reset(payload: ResetRequest, request: Request) -> dict:
    """Same answer whether or not the user exists."""
    with _public_session(payload.tenant_code) as db:
        reference = flows.request_reset(db, payload.username, _ip(request))
    return {"message": "If the account exists, its approver has been asked to confirm it is you. "
                       "Keep this reference: you need it to set a new password once approved.",
            "reference": reference}


@router.post("/password-resets/status")
def password_reset_status(payload: ResetReference) -> dict:
    with _public_session(payload.tenant_code) as db:
        return {"status": flows.reset_status(db, payload.reference)}


@router.post("/password-resets/complete")
def complete_password_reset(payload: ResetComplete) -> dict:
    with _public_session(payload.tenant_code) as db:
        try:
            username = flows.complete_reset(db, payload.reference, payload.new_password).username
        except flows.FlowError as e:
            raise _error(e)
    return {"message": f"Password set for {username}. Sign in with it now."}


@router.get("/password-resets/pending")
def pending_password_resets(db: Session = Depends(get_db),
                            current_user: UsvUser = Depends(get_current_user)) -> list[dict]:
    out = []
    for req in flows.pending_resets_for(db, current_user):
        person = db.get(UsvUser, req.user_id)
        out.append({"request_id": str(req.request_id), "username": person.username, "role": person.role,
                    "site_id": str(person.site_id) if person.site_id else None, "requested_at": req.created_at.isoformat(),
                    "source_ip": req.source_ip, "escalated": req.escalated_at is not None,
                    "approvals": len(req.approvals), "required_approvals": req.required_approvals})
    return out


@router.post("/password-resets/{request_id}/{decision}")
def decide_password_reset(request_id: uuid.UUID, decision: str, db: Session = Depends(get_db),
                          current_user: UsvUser = Depends(get_current_user)) -> dict:
    """decision: approve / reject. Approve only after confirming, through a
    separate channel (call or message), that it really is the person."""
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=404)
    try:
        req = flows.decide_reset(db, current_user, request_id, decision == "approve")
    except flows.FlowError as e:
        raise _error(e)
    return {"request_id": str(req.request_id), "status": req.status}


# ── break-glass ──

class BreakGlassAsk(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


def _bg_out(req: BreakGlassRequest) -> dict:
    return {"request_id": str(req.request_id), "site_id": str(req.site_id), "status": req.status,
            "reason": req.reason, "approvals": req.approvals, "created_at": req.created_at.isoformat(),
            "opened_at": req.opened_at.isoformat() if req.opened_at else None}


@router.post("/sites/{site_id}/break-glass/requests", status_code=201)
def request_break_glass(site_id: uuid.UUID, payload: BreakGlassAsk, db: Session = Depends(get_db),
                        current_user: UsvUser = Depends(require_role(*ADMINS))) -> dict:
    try:
        return _bg_out(flows.request_break_glass(db, current_user, site_id, payload.reason))
    except flows.FlowError as e:
        raise _error(e)


@router.get("/break-glass/requests")
def list_break_glass_requests(db: Session = Depends(get_db),
                              current_user: UsvUser = Depends(require_role(*ADMINS))) -> list[dict]:
    rows = db.execute(select(BreakGlassRequest).order_by(BreakGlassRequest.created_at.desc()).limit(200)).scalars()
    return [_bg_out(r) for r in rows if current_user.role == USV_PLATFORM_ADMIN or can_manage_site(db, current_user, r.site_id)]


@router.post("/break-glass/requests/{request_id}/approve")
def approve_break_glass(request_id: uuid.UUID, db: Session = Depends(get_db),
                        current_user: UsvUser = Depends(require_role(*ADMINS))) -> dict:
    try:
        return _bg_out(flows.approve_break_glass(db, current_user, request_id))
    except flows.FlowError as e:
        raise _error(e)


@router.post("/break-glass/requests/{request_id}/open")
def open_break_glass(request_id: uuid.UUID, db: Session = Depends(get_db),
                     current_user: UsvUser = Depends(require_role(*ADMINS))) -> dict:
    """Shows the break-glass password once to the requester after both
    approvals. Raises SE-03; the password is rotated 24 h later."""
    try:
        return flows.open_break_glass(db, current_user, request_id)
    except flows.FlowError as e:
        raise _error(e)


@router.post("/sites/{site_id}/break-glass/rotate")
def rotate_break_glass(site_id: uuid.UUID, db: Session = Depends(get_db),
                       current_user: UsvUser = Depends(require_role(USV_PLATFORM_ADMIN, USV_CUSTOMER_ADMIN))) -> dict:
    account = flows.rotate_break_glass(db, site_id, current_user)
    db.commit()
    return {"site_id": str(site_id), "rotated_at": account.rotated_at.isoformat()}
