import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import settings

_hasher = PasswordHasher()

ACCESS = "access"
REFRESH = "refresh"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _encode(subject: uuid.UUID, kind: str, secret: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "typ": kind,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def create_access_token(user_id: uuid.UUID) -> str:
    return _encode(user_id, ACCESS, settings.jwt_secret, timedelta(minutes=settings.access_token_minutes))


def create_refresh_token(user_id: uuid.UUID) -> str:
    return _encode(user_id, REFRESH, settings.jwt_refresh_secret, timedelta(days=settings.refresh_token_days))


def decode_token(token: str, kind: str) -> uuid.UUID | None:
    """Returns the user id, or None when the token is invalid, expired or of the
    wrong kind (an access token must never be usable as a refresh token)."""
    secret = settings.jwt_secret if kind == ACCESS else settings.jwt_refresh_secret
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != kind:
        return None
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None
