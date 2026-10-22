import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_ALGORITHM = "HS256"


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(plain_password, password_hash)


# Ingestion tokens (FR-1.4): same one-way hashing philosophy as user
# passwords, but named separately -- these are machine bearer credentials,
# not human passwords, and are never verified interactively.
def generate_ingestion_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_ingestion_secret(plain_secret: str) -> str:
    return _pwd_context.hash(plain_secret)


def verify_ingestion_secret(plain_secret: str, secret_hash: str) -> bool:
    return _pwd_context.verify(plain_secret, secret_hash)


def create_access_token(
    user_id: str,
    role: str,
    site_id: str | None,
    tenant_id: str | None = None,
    business_unit_id: str | None = None,
    tenant_db: bool = False,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "site_id": site_id,
        # tenant_id/business_unit_id (Section 3.5): tenant_id is what
        # app.core.tenancy's connection router keys off of in
        # MULTI_TENANT_POOL mode. Both are None in SINGLE_TENANT mode where
        # there is nothing to route between; harmless to carry regardless.
        "tenant_id": tenant_id,
        "business_unit_id": business_unit_id,
        # True when this user lives in a customer's own database
        # (MULTI_TENANT_POOL login with a tenant_code); app.core.rbac.get_db
        # routes the request there. False for platform users and in
        # SINGLE_TENANT mode, where tenant_id is informational only.
        "tenant_db": tenant_db,
        "iat": now,
        "exp": now + timedelta(minutes=settings.auth_token_expiry_minutes),
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.auth_secret_key, algorithms=[JWT_ALGORITHM])
