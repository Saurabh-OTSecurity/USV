import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_produces_hash_verify_password_confirms():
    plain = "CorrectHorseBatteryStaple1!"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True


def test_verify_password_rejects_incorrect_password():
    hashed = hash_password("CorrectHorseBatteryStaple1!")
    assert verify_password("WrongPassword!", hashed) is False


def test_create_and_decode_access_token_round_trips_claims():
    user_id = str(uuid.uuid4())
    site_id = str(uuid.uuid4())
    role = "usv_site_admin"

    token = create_access_token(user_id=user_id, role=role, site_id=site_id)
    payload = decode_access_token(token)

    assert payload["user_id"] == user_id
    assert payload["role"] == role
    assert payload["site_id"] == site_id
    assert "exp" in payload


def test_create_access_token_allows_null_site_id_for_platform_scoped_accounts():
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id=user_id, role="usv_platform_admin", site_id=None)
    payload = decode_access_token(token)
    assert payload["site_id"] is None


def test_decode_access_token_raises_on_tampered_token():
    token = create_access_token(user_id=str(uuid.uuid4()), role="usv_viewer", site_id=None)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered)


def test_decode_access_token_raises_on_invalid_token():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-real-token")


def test_decode_access_token_raises_on_expired_token():
    now = datetime.now(timezone.utc)
    expired_payload = {
        "user_id": str(uuid.uuid4()),
        "role": "usv_viewer",
        "site_id": None,
        "iat": now - timedelta(minutes=60),
        "exp": now - timedelta(minutes=30),
    }
    expired_token = jwt.encode(expired_payload, settings.auth_secret_key, algorithm=JWT_ALGORITHM)

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired_token)
