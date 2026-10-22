"""Single sign-on from USV into a site's Tribot (USV O&M Manual section 10,
option A, the user's decision), plus the directory each Tribot polls.

Assertion: a short-lived (settings.sso_assertion_seconds) Ed25519-signed
token USV issues to a signed-in person for one site. Claims: iss "usv", aud
"tribot:<site_code>", sub (username), name, role (Tribot's role), site_code,
iat, exp, jti. The Tribot verifies it with USV's public key, checks the
audience is its own site code, refuses a reused jti, and starts its own
session. People have no password on the Tribot.

Role mapping (Tribot has two roles): anyone who can manage the site (site,
BU, customer, platform admin) -> Admin; analysts and operators -> Engineer.
Viewers and auditors are refused: Tribot has no read-only role yet, and
silently granting Engineer would give them write access.

Directory (polled by the Tribot with its ingestion token, outbound only):
who may sign in there and with which role, when each person's sessions
were revoked, the break-glass account's Tribot-format hash, the password
policy, the site's approvers, and USV's public key.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import secrets_store
from app.core.config import settings
from app.core.rbac import USV_AUDITOR, USV_L1_OPERATOR, USV_L2_ANALYST, USV_VIEWER
from app.models.identity import Approver
from app.models.site import Site
from app.models.usv_user import UsvUser
from app.services.access_scope import can_manage_site, can_view_site
from app.services.identity_flows import ensure_break_glass
from app.services.password_policy import get_policy

ENGINEER_ROLES = {USV_L1_OPERATOR, USV_L2_ANALYST}
NO_TRIBOT_ROLE = {USV_VIEWER, USV_AUDITOR}


class SsoRefused(Exception):
    pass


def tribot_role(db: Session, user: UsvUser, site_id: uuid.UUID) -> str | None:
    if not can_view_site(db, user, site_id):
        return None
    if can_manage_site(db, user, site_id):
        return "Admin"
    if user.role in ENGINEER_ROLES:
        return "Engineer"
    return None


def public_key() -> dict:
    return {"alg": "EdDSA", "kid": secrets_store.key_id(), "public_key_pem": secrets_store.public_key_pem()}


def issue_assertion(db: Session, user: UsvUser, site: Site) -> dict:
    role = tribot_role(db, user, site.site_id)
    if role is None:
        reason = ("Tribot has no read-only role yet, so viewers and auditors can't sign in there"
                  if user.role in NO_TRIBOT_ROLE else "You don't have access to this site")
        raise SsoRefused(reason)
    now = datetime.now(timezone.utc)
    claims = {"iss": "usv", "aud": f"tribot:{site.site_code}", "sub": user.username,
              "name": user.display_name or user.username, "role": role, "site_code": site.site_code,
              "usv_user_id": str(user.user_id), "iat": now,
              "exp": now + timedelta(seconds=settings.sso_assertion_seconds), "jti": uuid.uuid4().hex}
    token = jwt.encode(claims, secrets_store.signing_key(), algorithm="EdDSA",
                       headers={"kid": secrets_store.key_id()})
    redirect = f"{site.tribot_url.rstrip('/')}/#/sso?assertion={token}" if site.tribot_url else None
    return {"assertion": token, "role": role, "expires_at": claims["exp"].isoformat(), "redirect_url": redirect}


def directory(db: Session, site: Site) -> dict:
    users = []
    for user in db.execute(select(UsvUser)).scalars():
        role = tribot_role(db, user, site.site_id) if user.status == "active" and user.locked_at is None else None
        if role is None:
            continue
        users.append({"username": user.username, "role": role, "name": user.display_name or user.username,
                      "sessions_revoked_before": user.sessions_revoked_before.isoformat()
                      if user.sessions_revoked_before else None})
    account = ensure_break_glass(db, site.site_id)
    policy = get_policy(db)
    approvers = db.execute(select(Approver, UsvUser.username).join(UsvUser, UsvUser.user_id == Approver.user_id).where(
        ((Approver.level == "site") & (Approver.scope_id == site.site_id))
        | ((Approver.level == "business_unit") & (Approver.scope_id == site.business_unit_id))
    )).all()
    db.commit()  # ensure_break_glass may have created the account
    return {
        "site_code": site.site_code,
        "site_id": str(site.site_id),
        "usv_ui_url": settings.ui_base_url.rstrip("/"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "users": users,
        "site_admins_configured": sum(1 for u in users if u["role"] == "Admin"),
        "break_glass": {"username": account.username, "password_hash": account.tribot_password_hash,
                        "rotated_at": account.rotated_at.isoformat()},
        "policy": {"min_length": policy.min_length, "history_count": policy.history_count,
                   "max_failed_logins": policy.max_failed_logins, "expiry_days": policy.expiry_days},
        "approvers": [{"username": name, "level": a.level, "is_backup": a.is_backup} for a, name in approvers],
        "usv_public_key": public_key(),
    }
