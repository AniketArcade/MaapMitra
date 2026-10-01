import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DB, require_roles
from app.core.roles import ADMIN_ROLES
from app.models.user import User
from app.schemas.audit import AuditLogOut
from app.schemas.common import Page, PageParams
from app.services import audit as audit_service

router = APIRouter(tags=["audit"])

# Spec 18 §4: widened from SUPER_ADMIN-only — list_audit_logs() now applies its own D4
# jurisdiction filter for a STATE_ADMIN actor (audit_logs has no jurisdiction column of its own).
# Spec 21 §4: widened again to DISTRICT_ADMIN, with a district-tightened version of the same
# filter.
Admin = Annotated[User, Depends(require_roles(*ADMIN_ROLES))]


@router.get("/audit-logs")
def list_audit_logs(
    actor: Admin,
    db: DB,
    paging: Annotated[PageParams, Depends()],
    date_from: date | None = None,
    date_to: date | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
) -> Page[AuditLogOut]:
    rows, total = audit_service.list_audit_logs(
        db,
        actor,
        date_from=date_from,
        date_to=date_to,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        limit=paging.page_size,
        offset=paging.offset,
    )
    return Page(
        items=[AuditLogOut.from_row(row, name) for row, name in rows],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )
