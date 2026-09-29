import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthError, Forbidden
from app.core.roles import Role
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


def get_client_ip(request: Request) -> str:
    """Client IP for rate limits and audit logs.

    With N trusted proxies each appending to X-Forwarded-For, the client is the Nth entry
    from the right. Entries further left are client-controlled and never trusted.
    """
    hops = get_settings().TRUSTED_PROXY_HOPS
    forwarded = request.headers.get("x-forwarded-for")
    if hops and forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DB,
) -> User:
    if creds is None:
        raise AuthError("Not authenticated")
    claims = decode_access_token(creds.credentials)
    try:
        user_id = uuid.UUID(claims["sub"])
    except ValueError as exc:
        raise AuthError("Invalid or expired token") from exc

    user = db.get(User, user_id)
    # Claims are a hint: the DB is the authority on role, org and active status.
    org_claim = claims.get("org_id")
    current_org = str(user.organization_id) if user and user.organization_id else None
    if (
        user is None
        or not user.is_active
        or claims.get("role") != user.role.value
        or org_claim != current_org
    ):
        raise AuthError("Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[..., User]:
    allowed = frozenset(roles)

    def dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise Forbidden("Insufficient permissions")
        return user

    return dependency
