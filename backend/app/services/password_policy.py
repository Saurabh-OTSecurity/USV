"""Password policy and lockout for USV users (USV O&M Manual section 10).

Starting values from the manual: at least 14 characters, not one of the last
5 passwords, 5 failed logins lock the account, a change is required at first
login for every issued or reset password, expiry optional per customer.
Setting a password also ends the person's other sessions
(sessions_revoked_before), so a reset really locks out whoever had it.
"""
import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.identity import PasswordPolicy
from app.models.usv_user import UsvUser


def get_policy(db: Session) -> PasswordPolicy:
    policy = db.get(PasswordPolicy, 1)
    if policy is None:
        policy = PasswordPolicy(policy_id=1)
        db.add(policy)
        db.flush()
    return policy


def validate_new_password(db: Session, user: UsvUser, password: str) -> list[str]:
    policy = get_policy(db)
    problems = []
    if len(password) < policy.min_length:
        problems.append(f"Must be at least {policy.min_length} characters")
    if user.username and user.username.lower() in password.lower():
        problems.append("Must not contain the user name")
    recent = [user.password_hash] + list(user.password_history or [])[: max(policy.history_count - 1, 0)]
    if any(h and verify_password(password, h) for h in recent):
        problems.append(f"Must not be one of the last {policy.history_count} passwords")
    return problems


def set_password(db: Session, user: UsvUser, password: str, *, must_change: bool = False,
                 now: datetime | None = None) -> None:
    """Stores the new password, keeps history, clears any lockout and ends
    the person's existing sessions. Caller validates and commits."""
    now = now or datetime.now(timezone.utc)
    policy = get_policy(db)
    history = ([user.password_hash] if user.password_hash else []) + list(user.password_history or [])
    user.password_history = history[: policy.history_count]
    user.password_hash = hash_password(password)
    user.password_changed_at = now
    user.must_change_password = must_change
    user.failed_login_count, user.locked_at = 0, None
    user.sessions_revoked_before = now


def end_sessions(user: UsvUser, now: datetime | None = None) -> None:
    """Every token issued to this person before now stops working, in USV
    at once and on each Tribot at its next directory poll."""
    user.sessions_revoked_before = now or datetime.now(timezone.utc)


def generate_temporary_password(length: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "-_.!@#"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in candidate) and any(c.isupper() for c in candidate)
                and any(c.isdigit() for c in candidate)):
            return candidate


def is_expired(db: Session, user: UsvUser, now: datetime | None = None) -> bool:
    policy = get_policy(db)
    if not policy.expiry_days or user.password_changed_at is None:
        return False
    return (now or datetime.now(timezone.utc)) - user.password_changed_at > timedelta(days=policy.expiry_days)


def register_failed_login(db: Session, user: UsvUser, now: datetime | None = None) -> bool:
    """Counts a failed login; returns True if this one locked the account."""
    policy = get_policy(db)
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.locked_at is None and user.failed_login_count >= policy.max_failed_logins:
        user.locked_at = now or datetime.now(timezone.utc)
        return True
    return False
