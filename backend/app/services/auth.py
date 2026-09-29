from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AuthError, Conflict, RateLimited
from app.core.rate_limit import login_email_window
from app.core.roles import OrgType, Role
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    hash_token,
    needs_rehash,
    new_refresh_token,
    refresh_ttl,
    verify_password,
)
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services import audit

# A revoked token seen again within this window is a lost refresh race, not theft.
REUSE_GRACE = timedelta(seconds=10)
INVALID_CREDENTIALS = "Invalid email or password"
INVALID_SESSION = "Session expired. Please log in again."


@dataclass(frozen=True)
class AuthResult:
    user: User
    access_token: str
    refresh_token: str


def _now() -> datetime:
    return datetime.now(UTC)


def issue_tokens(db: Session, user: User) -> AuthResult:
    """Add a refresh-token row to the session. The caller commits."""
    raw = new_refresh_token()
    db.add(
        RefreshToken(user_id=user.id, token_hash=hash_token(raw), expires_at=_now() + refresh_ttl())
    )
    return AuthResult(user=user, access_token=create_access_token(user), refresh_token=raw)


def register(db: Session, body: RegisterRequest, *, ip: str) -> AuthResult:
    org = Organization(
        type=OrgType.BUSINESS,
        name=body.organization_name,
        registration_number=body.registration_number,
        address=body.address,
        state_code=body.state_code,
        district_code=body.district_code,
    )
    user = User(
        email=body.email,
        password_hash=hash_password(body.password.get_secret_value()),
        full_name=body.full_name,
        phone=body.phone,
        role=Role.BUSINESS,  # never client-chosen
        organization=org,
    )
    db.add_all([org, user])
    try:
        db.flush()  # the unique index on users.email is the source of truth (also covers races)
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Email already registered") from exc

    audit.log(
        db,
        action="USER_REGISTERED",
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        org_id=org.id,
        details={"organization_name": org.name},
        ip=ip,
    )
    result = issue_tokens(db, user)
    db.commit()
    return result


def login(db: Session, body: LoginRequest, *, ip: str) -> AuthResult:
    if not login_email_window.hit(body.email):
        raise RateLimited("Too many login attempts. Try again in a minute.")

    password = body.password.get_secret_value()
    user = db.scalar(select(User).where(User.email == body.email))
    # Always run one Argon2 verify so timing doesn't reveal whether the email exists.
    password_ok = verify_password(user.password_hash if user else DUMMY_HASH, password)

    if user is None or not user.is_active or not password_ok:
        reason = (
            "unknown_email"
            if user is None
            else "inactive"
            if not user.is_active
            else "bad_password"
        )
        audit.log(db, action="LOGIN_FAILED", details={"email": body.email, "reason": reason}, ip=ip)
        db.commit()  # commit-then-raise: the evidence must survive the error
        raise AuthError(INVALID_CREDENTIALS)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = _now()
    audit.log(
        db,
        action="LOGIN_SUCCEEDED",
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        org_id=user.organization_id,
        ip=ip,
    )
    result = issue_tokens(db, user)
    db.commit()
    return result


def refresh(db: Session, raw_token: str | None, *, ip: str) -> AuthResult:
    if not raw_token:
        raise AuthError(INVALID_SESSION, clear_cookies=True)

    # Row lock serialises concurrent refreshes of the same token.
    row = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .with_for_update()
    )
    now = _now()
    if row is None:
        db.rollback()
        raise AuthError(INVALID_SESSION, clear_cookies=True)

    if row.revoked_at is not None:
        if now - row.revoked_at < REUSE_GRACE:
            # Lost a race: the winner already set fresh cookies, so leave them alone.
            db.rollback()
            raise AuthError(INVALID_SESSION, clear_cookies=False)
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        audit.log(
            db,
            action="REFRESH_REUSE_DETECTED",
            actor_id=row.user_id,
            entity_type="user",
            entity_id=row.user_id,
            details={"token_id": str(row.id)},
            ip=ip,
        )
        db.commit()  # commit-then-raise
        raise AuthError(INVALID_SESSION, clear_cookies=True)

    user = db.get(User, row.user_id)
    if row.expires_at <= now or user is None or not user.is_active:
        db.rollback()
        raise AuthError(INVALID_SESSION, clear_cookies=True)

    row.revoked_at = now
    result = issue_tokens(db, user)
    db.commit()
    return result


def logout(db: Session, raw_token: str | None, *, ip: str) -> None:
    """Idempotent: a missing, unknown or already-revoked token is not an error."""
    if not raw_token:
        return
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    if row is None or row.revoked_at is not None:
        return
    row.revoked_at = _now()
    audit.log(
        db, action="LOGOUT", actor_id=row.user_id, entity_type="user", entity_id=row.user_id, ip=ip
    )
    db.commit()
