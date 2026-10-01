import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.application_types import TERMINAL_STATUSES
from app.core.errors import Conflict, Forbidden, NotFound
from app.core.roles import OFFICIAL_ROLES, Role
from app.core.security import hash_password
from app.models.application import Application
from app.models.inspection import Inspection
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import audit


def create_user(db: Session, actor: User, body: UserCreate, *, ip: str) -> User:
    if actor.role != Role.SUPER_ADMIN:  # defence in depth; the router also enforces this
        raise Forbidden("Insufficient permissions")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password.get_secret_value()),
        full_name=body.full_name,
        phone=body.phone,
        role=Role(body.role),
        state_code=body.state_code,
        district_code=body.district_code,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Email already registered") from exc

    audit.log(
        db,
        action="USER_CREATED",
        actor=actor.id,
        entity_type="user",
        entity_id=user.id,
        details={
            "role": user.role.value,
            "state_code": user.state_code,
            "district_code": user.district_code,
        },
        ip=ip,
    )
    db.commit()
    return user


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_users(
    db: Session,
    *,
    role: Role | None,
    state_code: str | None,
    district_code: str | None,
    is_active: bool | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[User], dict[uuid.UUID, tuple[int, int]], int]:
    """Spec 17 D2: official accounts only (role in OFFICIAL_ROLES) — never BUSINESS/GATC, which
    aren't managed on this page. Case counts (second return value, keyed by user id) are only
    computed when filtering to role=LM_OFFICER (the LMO directory, spec 17 §6.5) — a user_id not
    present in that dict means "not requested," not "zero."""
    stmt = select(User).where(User.role.in_(OFFICIAL_ROLES))
    if role is not None:
        stmt = stmt.where(User.role == role)
    if state_code:
        stmt = stmt.where(User.state_code == state_code)
    if district_code:
        stmt = stmt.where(User.district_code == district_code)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if q:
        pattern = f"%{_escape_like(q)}%"
        stmt = stmt.where(
            or_(
                User.full_name.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        db.scalars(stmt.order_by(User.created_at.desc(), User.id).limit(limit).offset(offset))
    )

    counts: dict[uuid.UUID, tuple[int, int]] = {}
    if role == Role.LM_OFFICER and items:
        ids = [u.id for u in items]
        rows = db.execute(
            select(
                Inspection.assigned_officer_id,
                func.count().filter(Application.status.notin_(TERMINAL_STATUSES)),
                func.count().filter(Application.status.in_(TERMINAL_STATUSES)),
            )
            .select_from(Inspection)
            .join(Application, Application.id == Inspection.application_id)
            .where(Inspection.assigned_officer_id.in_(ids))
            .group_by(Inspection.assigned_officer_id)
        ).all()
        counts = {uid: (pending, completed) for uid, pending, completed in rows}
    return items, counts, total


def set_active(db: Session, actor: User, user_id: uuid.UUID, is_active: bool, *, ip: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    if user.id == actor.id and not is_active:
        # A lone Super Admin deactivating themselves would be an unrecoverable lockout — nobody
        # left with permission to re-enable the account.
        raise Conflict("Cannot deactivate your own account")
    user.is_active = is_active
    audit.log(
        db,
        actor=actor,
        action="USER_STATUS_CHANGED",
        entity_type="user",
        entity_id=user.id,
        details={"is_active": is_active, "role": user.role.value},
        ip=ip,
    )
    db.commit()
    return user
