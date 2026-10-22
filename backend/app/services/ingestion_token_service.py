import hashlib
import hmac
import threading
import time
import uuid

from sqlalchemy.orm import Session

from app.core.security import generate_ingestion_secret, hash_ingestion_secret, verify_ingestion_secret
from app.models.ingestion_token import IngestionToken
from app.models.site import Site
from app.repositories.ingestion_token_repository import IngestionTokenRepository


class SiteNotFoundError(Exception):
    pass


class InvalidIngestionCredentialError(Exception):
    """reason: malformed / unknown_token / revoked / bad_secret. Recorded for
    the rejected-connections alert (SU-08); never returned to the caller."""

    def __init__(self, reason: str = "malformed", token_id: uuid.UUID | None = None,
                 site_id: uuid.UUID | None = None):
        super().__init__(reason)
        self.reason, self.token_id, self.site_id = reason, token_id, site_id


# bcrypt costs ~0.3 s per check by design. With hundreds of sites pushing,
# re-running it on every request would make token checks the bottleneck, so
# a successful check is remembered briefly, keyed by token_id and bound to
# both a SHA-256 of the presented secret and the stored secret_hash (a
# rotated hash invalidates it). The token row is still read on every request,
# so a revoked token is refused immediately -- the cache only skips bcrypt.
VERIFIED_SECRET_TTL_SECONDS = 300
_verified_secrets: dict[uuid.UUID, tuple[str, str, float]] = {}
_verified_lock = threading.Lock()


def _secret_digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _recently_verified(token: IngestionToken, secret: str) -> bool:
    with _verified_lock:
        entry = _verified_secrets.get(token.token_id)
    if entry is None:
        return False
    digest, secret_hash, expires_at = entry
    return (time.monotonic() < expires_at and secret_hash == token.secret_hash
            and hmac.compare_digest(digest, _secret_digest(secret)))


def _remember_verified(token: IngestionToken, secret: str) -> None:
    with _verified_lock:
        _verified_secrets[token.token_id] = (
            _secret_digest(secret), token.secret_hash, time.monotonic() + VERIFIED_SECRET_TTL_SECONDS
        )


class IngestionTokenService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = IngestionTokenRepository(db)

    def issue_token(self, site_id: uuid.UUID) -> tuple[IngestionToken, str]:
        """Returns (row, plaintext_token). The plaintext is never
        recoverable again after this call returns -- only secret_hash is
        persisted."""
        if self.db.get(Site, site_id) is None:
            raise SiteNotFoundError(site_id)

        secret = generate_ingestion_secret()
        token = self.repository.create(
            IngestionToken(site_id=site_id, secret_hash=hash_ingestion_secret(secret), status="active")
        )
        plaintext = f"{token.token_id}.{secret}"
        return token, plaintext

    def list_for_site(self, site_id: uuid.UUID) -> list[IngestionToken]:
        return self.repository.list_for_site(site_id)

    def revoke(self, token_id: uuid.UUID) -> IngestionToken | None:
        token = self.repository.get_by_id(token_id)
        if token is None:
            return None
        return self.repository.revoke(token)

    def authenticate(self, presented_token: str) -> IngestionToken:
        """Parses "<token_id>.<secret>", looks the row up by token_id (fast,
        indexed), then verifies the secret against its hash -- never scans
        every active token. Raises InvalidIngestionCredentialError on any
        failure (bad shape, unknown token_id, revoked, wrong secret). Its
        reason is only recorded internally (rejected-connections alert); the
        HTTP answer is the same for all of them, so a probing attacker learns
        nothing extra."""
        try:
            token_id_str, secret = presented_token.split(".", 1)
            token_id = uuid.UUID(token_id_str)
        except (ValueError, AttributeError):
            raise InvalidIngestionCredentialError("malformed")

        token = self.repository.get_by_id(token_id)
        if token is None:
            raise InvalidIngestionCredentialError("unknown_token", token_id)
        if token.status != "active":
            raise InvalidIngestionCredentialError("revoked", token_id, token.site_id)
        if not _recently_verified(token, secret):
            if not verify_ingestion_secret(secret, token.secret_hash):
                raise InvalidIngestionCredentialError("bad_secret", token_id, token.site_id)
            _remember_verified(token, secret)

        self.repository.mark_used(token)
        return token
