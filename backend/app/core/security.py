import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import AuthError
from app.models.user import User

ALGORITHM = "HS256"

_hasher = PasswordHasher()  # Argon2id with library defaults
# Verified against when the email is unknown, so login timing doesn't reveal which emails exist.
DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def access_ttl() -> timedelta:
    return timedelta(minutes=get_settings().JWT_ACCESS_TTL_MIN)


def refresh_ttl() -> timedelta:
    return timedelta(days=get_settings().JWT_REFRESH_TTL_DAYS)


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user.id),
        "role": user.role.value,
        "org_id": str(user.organization_id) if user.organization_id else None,
        "type": "access",
        "iat": now,
        "exp": now + access_ttl(),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, get_settings().JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            get_settings().JWT_SECRET,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired token") from exc
    if claims.get("type") != "access":
        raise AuthError("Invalid or expired token")
    return claims


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
