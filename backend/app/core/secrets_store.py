"""USV's two private keys, kept as files under settings.secrets_dir and
created on first use:

- the encryption key (Fernet) for secrets USV must be able to read back:
  break-glass passwords and one-time secure shares;
- the Ed25519 signing key for single sign-on assertions to Tribot. Tribots
  verify with the public half (GET /api/v1/sso/public-key), so a Tribot never
  holds anything that could forge a login.

The files are written with owner-only permissions where the OS supports it.
"""
import base64
import hashlib
import os
import threading

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import settings

_lock = threading.Lock()
_fernet: Fernet | None = None
_signing_key: Ed25519PrivateKey | None = None


def _path(name: str) -> str:
    return os.path.join(settings.secrets_dir, name)


def _write_private(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def _fernet_instance() -> Fernet:
    global _fernet
    with _lock:
        if _fernet is None:
            path = _path("secret_box.key")
            if not os.path.exists(path):
                _write_private(path, Fernet.generate_key())
            with open(path, "rb") as f:
                _fernet = Fernet(f.read().strip())
        return _fernet


def encrypt(plaintext: str) -> str:
    return _fernet_instance().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet_instance().decrypt(token.encode()).decode()


def signing_key() -> Ed25519PrivateKey:
    global _signing_key
    with _lock:
        if _signing_key is None:
            path = _path("sso_ed25519.pem")
            if not os.path.exists(path):
                key = Ed25519PrivateKey.generate()
                _write_private(path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                       serialization.NoEncryption()))
            with open(path, "rb") as f:
                _signing_key = serialization.load_pem_private_key(f.read(), password=None)
        return _signing_key


def public_key_pem() -> str:
    return signing_key().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def key_id() -> str:
    """Short stable id of the signing key (changes if the key is replaced)."""
    raw = signing_key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.urlsafe_b64encode(hashlib.sha256(raw).digest()[:12]).decode().rstrip("=")


def reset_for_tests() -> None:
    global _fernet, _signing_key
    with _lock:
        _fernet, _signing_key = None, None
