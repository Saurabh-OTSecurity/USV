"""Secure shares, approved password resets and break-glass accounts
(USV O&M Manual sections 10-11). Notifications are in-app only for now.

Secure share: a capability link (/share/<token>) that reveals a secret once
and expires (policy share_link_hours, 24 h). Only the token's hash is
stored; the secret is encrypted and destroyed when opened or expired.

Password reset: anyone can ask (the answer is the same whether or not the
user exists, so it reveals nothing). The requester gets a reference only they
see; the approver confirms identity out of band and approves; the requester
then sets a new password with the reference, once, within reset_link_minutes.
Pending longer than reset_approval_hours: the backup approvers are notified
and SE-02 is raised. The link never goes to the approver.

Break-glass: one local emergency account per site's Tribot. USV generates and
rotates the password and gives Tribot only its own-format hash. Opening it
needs two approvals -- one from the customer side, one from Tribastion
(a platform admin) -- then the requester sees it once, SE-03 is raised, and
the password is rotated 24 h later.
"""
import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import secrets_store
from app.core.rbac import USV_PLATFORM_ADMIN
from app.models.audit_log import AuditLog
from app.models.identity import BreakGlassAccount, BreakGlassRequest, PasswordResetRequest, SecureShare
from app.models.monitoring import UsvNotification
from app.models.site import Site
from app.models.usv_user import UsvUser
from app.services import approvals
from app.services.access_scope import can_manage_site
from app.services.monitoring.alerts import clear_alert, raise_alert, record_event
from app.services.password_policy import (
    generate_temporary_password, get_policy, set_password, validate_new_password,
)

BREAK_GLASS_ROTATE_AFTER = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _audit(db: Session, event_type: str, actor=None, result="success", detail=None, target_type=None, target_id=None):
    db.add(AuditLog(occurred_at=_now(), event_type=event_type, actor_user_id=getattr(actor, "user_id", actor),
                    result=result, target_type=target_type, target_id=target_id, detail=detail or {}))


def _notify(db: Session, user_ids, title: str, level: str) -> None:
    for uid in user_ids:
        db.add(UsvNotification(user_id=uid, level=level, title=title, created_at=_now()))


class FlowError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# ── secure shares ──

def create_initial_password_share(db: Session, admin: UsvUser, target: UsvUser) -> tuple[str, datetime]:
    """Gives `target` a fresh temporary password (change required at first
    login) and returns (one-time link token, expiry). The password itself
    is never returned to the admin."""
    password = generate_temporary_password()
    set_password(db, target, password, must_change=True)
    token = secrets.token_urlsafe(32)
    expires = _now() + timedelta(hours=get_policy(db).share_link_hours)
    db.add(SecureShare(token_hash=_hash(token), purpose="initial_password", target_user_id=target.user_id,
                       secret_encrypted=secrets_store.encrypt(password), created_by=admin.user_id, expires_at=expires))
    _audit(db, "secure_share_created", admin, detail={"purpose": "initial_password", "for": target.username,
                                                      "expires_at": expires.isoformat()})
    return token, expires


def open_share(db: Session, token: str, source_ip: str | None = None) -> dict:
    share = db.execute(select(SecureShare).where(SecureShare.token_hash == _hash(token))).scalar_one_or_none()
    if share is None:
        _audit(db, "secure_share_open_failed", result="failure", detail={"reason": "unknown", "ip": source_ip})
        db.commit()
        raise FlowError("SHARE_NOT_FOUND", "This link is not valid", 404)
    if share.opened_at is not None or share.secret_encrypted is None or _now() >= share.expires_at:
        share.failed_attempts += 1
        share.secret_encrypted = None
        _audit(db, "secure_share_open_failed", result="failure",
               detail={"reason": "used" if share.opened_at else "expired", "share_id": str(share.share_id), "ip": source_ip})
        db.commit()
        raise FlowError("SHARE_GONE", "This link was already used or has expired", 410)
    secret = secrets_store.decrypt(share.secret_encrypted)
    share.secret_encrypted, share.opened_at = None, _now()
    target = db.get(UsvUser, share.target_user_id) if share.target_user_id else None
    _audit(db, "secure_share_opened", detail={"share_id": str(share.share_id), "purpose": share.purpose,
                                              "for": target.username if target else None, "ip": source_ip})
    db.commit()
    return {"purpose": share.purpose, "username": target.username if target else None, "secret": secret}


# ── approved password reset ──

def request_reset(db: Session, username: str, source_ip: str | None) -> str:
    """Always returns a reference, whether or not the user exists."""
    reference = secrets.token_urlsafe(24)
    user = db.execute(select(UsvUser).where(UsvUser.username == username)).scalar_one_or_none()
    if user is None or user.status != "active":
        _audit(db, "password_reset_requested", result="ignored", detail={"username": username, "ip": source_ip})
        db.commit()
        return reference
    primary, _, required = approvals.approvers_for(db, user)
    req = PasswordResetRequest(user_id=user.user_id, reference_hash=_hash(reference), required_approvals=required,
                               source_ip=source_ip)
    db.add(req)
    db.flush()
    _notify(db, primary, f"Password reset requested by {user.username} (from {source_ip or 'unknown'})", "approver")
    _audit(db, "password_reset_requested", user, detail={"request_id": str(req.request_id), "ip": source_ip,
                                                         "approvers": [str(u) for u in primary]})
    db.commit()
    return reference


def pending_resets_for(db: Session, approver: UsvUser) -> list[PasswordResetRequest]:
    rows = db.execute(select(PasswordResetRequest).where(PasswordResetRequest.status == "pending")).scalars().all()
    out = []
    for req in rows:
        person = db.get(UsvUser, req.user_id)
        if person is not None and approvals.may_approve(db, approver, person, req.escalated_at is not None) \
                and str(approver.user_id) not in [a["user_id"] for a in req.approvals]:
            out.append(req)
    return out


def decide_reset(db: Session, approver: UsvUser, request_id: uuid.UUID, approve: bool) -> PasswordResetRequest:
    req = db.get(PasswordResetRequest, request_id)
    if req is None or req.status != "pending":
        raise FlowError("NOT_PENDING", "This request is not waiting for a decision", 404)
    person = db.get(UsvUser, req.user_id)
    if not approvals.may_approve(db, approver, person, req.escalated_at is not None):
        raise FlowError("NOT_AN_APPROVER", "You are not an approver for this person", 403)
    if any(a["user_id"] == str(approver.user_id) for a in req.approvals):
        raise FlowError("ALREADY_APPROVED", "You already approved this request")
    if not approve:
        req.status, req.decided_at, req.decided_by = "rejected", _now(), approver.user_id
    else:
        req.approvals = list(req.approvals) + [{"user_id": str(approver.user_id), "at": _now().isoformat()}]
        if len(req.approvals) >= req.required_approvals:
            req.status, req.decided_at, req.decided_by = "approved", _now(), approver.user_id
    _audit(db, "password_reset_" + ("approved" if approve else "rejected"), approver,
           detail={"request_id": str(req.request_id), "for": person.username, "status": req.status})
    clear_alert(db, f"SE-02|{req.request_id}")
    db.commit()
    return req


def reset_status(db: Session, reference: str) -> str:
    req = db.execute(select(PasswordResetRequest).where(
        PasswordResetRequest.reference_hash == _hash(reference))).scalar_one_or_none()
    if req is None:
        return "pending"  # unknown references look like waiting ones: reveals nothing
    if req.status == "approved" and _now() - req.decided_at > timedelta(minutes=get_policy(db).reset_link_minutes):
        req.status = "expired"
        db.commit()
    return req.status


def complete_reset(db: Session, reference: str, new_password: str) -> UsvUser:
    req = db.execute(select(PasswordResetRequest).where(
        PasswordResetRequest.reference_hash == _hash(reference))).scalar_one_or_none()
    if req is None or reset_status(db, reference) != "approved":
        raise FlowError("NOT_APPROVED", "This reset is not approved, or its time ran out", 409)
    user = db.get(UsvUser, req.user_id)
    problems = validate_new_password(db, user, new_password)
    if problems:
        raise FlowError("PASSWORD_POLICY", "; ".join(problems), 422)
    set_password(db, user, new_password)
    req.status, req.completed_at = "completed", _now()
    _audit(db, "password_reset_completed", user, detail={"request_id": str(req.request_id)})
    db.commit()
    return user


def escalate_stale_resets(db: Session, now: datetime | None = None) -> int:
    """Called by the monitoring loop: requests pending past the approval time
    go to the backup approvers and raise SE-02."""
    now = now or _now()
    limit = timedelta(hours=get_policy(db).reset_approval_hours)
    count = 0
    for req in db.execute(select(PasswordResetRequest).where(PasswordResetRequest.status == "pending")).scalars():
        if now - req.created_at < limit:
            continue
        person = db.get(UsvUser, req.user_id)
        if req.escalated_at is None:
            _, backups, _ = approvals.approvers_for(db, person)
            _notify(db, backups, f"Escalated: password reset for {person.username} waiting since "
                                 f"{req.created_at.isoformat()}", "approver_backup")
            req.escalated_at = now
            count += 1
        raise_alert(db, rule_id="SE-02", dedupe_key=f"SE-02|{req.request_id}", category="Security", severity="Warning",
                    site_id=person.site_id, title=f"Password reset for {person.username} waiting too long",
                    detail={"request_id": str(req.request_id), "since": req.created_at.isoformat()}, now=now)
    return count


# ── break-glass ──

def _tribot_hash(password: str) -> str:
    """Tribot's own format (app/auth.py hash_password): PBKDF2-HMAC-SHA256,
    100,000 iterations, "<salt_hex>:<key_hex>"."""
    salt = os.urandom(32)
    return salt.hex() + ":" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000).hex()


def rotate_break_glass(db: Session, site_id: uuid.UUID, actor=None) -> BreakGlassAccount:
    password = generate_temporary_password(24)
    account = db.get(BreakGlassAccount, site_id)
    now = _now()
    if account is None:
        account = BreakGlassAccount(site_id=site_id, password_encrypted="", tribot_password_hash="", rotated_at=now)
        db.add(account)
    account.password_encrypted = secrets_store.encrypt(password)
    account.tribot_password_hash = _tribot_hash(password)
    account.rotated_at, account.rotate_due_at = now, None
    _audit(db, "break_glass_rotated", actor, detail={"site_id": str(site_id)})
    return account


def ensure_break_glass(db: Session, site_id: uuid.UUID) -> BreakGlassAccount:
    return db.get(BreakGlassAccount, site_id) or rotate_break_glass(db, site_id)


def request_break_glass(db: Session, requester: UsvUser, site_id: uuid.UUID, reason: str) -> BreakGlassRequest:
    if not can_manage_site(db, requester, site_id):
        raise FlowError("FORBIDDEN", "You can only request break-glass for your own sites", 403)
    req = BreakGlassRequest(site_id=site_id, requested_by=requester.user_id, reason=reason)
    db.add(req)
    db.flush()
    site = db.get(Site, site_id)
    platform_admins = db.execute(select(UsvUser.user_id).where(
        UsvUser.role == USV_PLATFORM_ADMIN, UsvUser.status == "active")).scalars().all()
    _notify(db, [u for u in platform_admins if u != requester.user_id],
            f"Break-glass requested for {site.site_code}: {reason}", "approver")
    _audit(db, "break_glass_requested", requester, detail={"site_id": str(site_id), "reason": reason})
    db.commit()
    return req


def approve_break_glass(db: Session, approver: UsvUser, request_id: uuid.UUID) -> BreakGlassRequest:
    req = db.get(BreakGlassRequest, request_id)
    if req is None or req.status != "pending":
        raise FlowError("NOT_PENDING", "This request is not waiting for approval", 404)
    if approver.user_id == req.requested_by or any(a["user_id"] == str(approver.user_id) for a in req.approvals):
        raise FlowError("NOT_ALLOWED", "The requester or an earlier approver cannot approve", 403)
    side = "tribastion" if approver.role == USV_PLATFORM_ADMIN else (
        "customer" if can_manage_site(db, approver, req.site_id) else None)
    if side is None:
        raise FlowError("NOT_AN_APPROVER", "You are not an approver for this site", 403)
    if any(a["side"] == side for a in req.approvals):
        raise FlowError("SIDE_DONE", f"The {side} approval is already given; the other side must approve")
    req.approvals = list(req.approvals) + [{"user_id": str(approver.user_id), "side": side, "at": _now().isoformat()}]
    if {a["side"] for a in req.approvals} == {"customer", "tribastion"}:
        req.status = "approved"
    _audit(db, "break_glass_approved", approver, detail={"request_id": str(req.request_id), "side": side})
    db.commit()
    return req


def open_break_glass(db: Session, requester: UsvUser, request_id: uuid.UUID) -> dict:
    req = db.get(BreakGlassRequest, request_id)
    if req is None or req.requested_by != requester.user_id:
        raise FlowError("NOT_FOUND", "Request not found", 404)
    if req.status != "approved":
        raise FlowError("NOT_APPROVED", "Two approvals (customer and Tribastion) are needed first")
    account = ensure_break_glass(db, req.site_id)
    password = secrets_store.decrypt(account.password_encrypted)
    now = _now()
    req.status, req.opened_at = "opened", now
    account.rotate_due_at = now + BREAK_GLASS_ROTATE_AFTER
    site = db.get(Site, req.site_id)
    record_event(db, rule_id="SE-03", category="Security", severity="Critical", site_id=req.site_id,
                 title=f"Break-glass account opened for {site.site_code} by {requester.username}",
                 detail={"request_id": str(req.request_id), "reason": req.reason, "approvals": req.approvals})
    _audit(db, "break_glass_opened", requester, detail={"request_id": str(req.request_id), "site_id": str(req.site_id)})
    db.commit()
    return {"username": account.username, "password": password, "rotates_at": account.rotate_due_at.isoformat()}


def rotate_due_break_glass(db: Session, now: datetime | None = None) -> int:
    now = now or _now()
    due = db.execute(select(BreakGlassAccount).where(BreakGlassAccount.rotate_due_at <= now)).scalars().all()
    for account in due:
        rotate_break_glass(db, account.site_id)
    return len(due)
