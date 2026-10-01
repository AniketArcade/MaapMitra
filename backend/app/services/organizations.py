import uuid

from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from app.core.application_types import TERMINAL_STATUSES
from app.core.roles import OrgType, Role
from app.models.application import Application
from app.models.inspection import Inspection
from app.models.instrument_category import InstrumentCategory
from app.models.organization import Organization
from app.models.user import User
from app.services.scoping import scope_organizations


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def gatc_directory(
    db: Session,
    user: User,
    *,
    state_code: str | None,
    district_code: str | None,
    q: str | None,
    is_active: bool | None,
    limit: int,
    offset: int,
) -> tuple[
    list[Organization],
    dict[uuid.UUID, tuple[int, int]],
    dict[uuid.UUID, list[User]],
    dict[int, str],
    dict[uuid.UUID, bool],
    int,
]:
    """Spec 17 §6.5: the GATC directory. Returns (page of orgs, {org_id: (pending, completed)},
    {org_id: [GATC users]}, {category_id: name}, {org_id: has_active_user}, total).

    Uses scope_organizations() even though SUPER_ADMIN's own branch is a no-op today (this
    endpoint is SUPER_ADMIN-only) — future-proofs for free if a narrower admin role ever reuses
    this directory (spec 17 §5), at zero extra query cost.
    """
    stmt = scope_organizations(select(Organization), user).where(Organization.type == OrgType.GATC)
    if state_code:
        stmt = stmt.where(Organization.state_code == state_code)
    if district_code:
        stmt = stmt.where(Organization.district_code == district_code)
    if q:
        stmt = stmt.where(Organization.name.ilike(f"%{_escape_like(q)}%", escape="\\"))
    if is_active is not None:
        active_exists = exists().where(
            User.organization_id == Organization.id,
            User.role == Role.GATC,
            User.is_active.is_(True),
        )
        stmt = stmt.where(active_exists if is_active else ~active_exists)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    orgs = list(db.scalars(stmt.order_by(Organization.name).limit(limit).offset(offset)))
    org_ids = [o.id for o in orgs]
    if not org_ids:
        return orgs, {}, {}, {}, {}, total

    count_rows = db.execute(
        select(
            Organization.id,
            func.count().filter(Application.status.notin_(TERMINAL_STATUSES)),
            func.count().filter(Application.status.in_(TERMINAL_STATUSES)),
        )
        .select_from(Organization)
        .outerjoin(User, and_(User.organization_id == Organization.id, User.role == Role.GATC))
        .outerjoin(Inspection, Inspection.assigned_officer_id == User.id)
        .outerjoin(Application, Application.id == Inspection.application_id)
        .where(Organization.id.in_(org_ids))
        .group_by(Organization.id)
    ).all()
    counts = {org_id: (pending, completed) for org_id, pending, completed in count_rows}

    org_users = list(
        db.scalars(
            select(User)
            .where(User.organization_id.in_(org_ids), User.role == Role.GATC)
            .order_by(User.full_name)
        )
    )
    users_by_org: dict[uuid.UUID, list[User]] = {}
    has_active: dict[uuid.UUID, bool] = {}
    for u in org_users:
        users_by_org.setdefault(u.organization_id, []).append(u)
        has_active[u.organization_id] = has_active.get(u.organization_id, False) or u.is_active

    all_cat_ids = {cid for o in orgs for cid in (o.gatc_eligible_category_ids or [])}
    cat_names: dict[int, str] = {}
    if all_cat_ids:
        cat_names = dict(
            db.execute(
                select(InstrumentCategory.id, InstrumentCategory.name).where(
                    InstrumentCategory.id.in_(all_cat_ids)
                )
            ).all()
        )

    return orgs, counts, users_by_org, cat_names, has_active, total
