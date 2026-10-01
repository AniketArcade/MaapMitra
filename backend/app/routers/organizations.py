from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.core.deps import DB, require_roles
from app.core.roles import ADMIN_ROLES
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.organization import GatcDirectoryOut, GatcDirectoryUserOut
from app.services import organizations as org_service

router = APIRouter(prefix="/organizations", tags=["organizations"])

# Spec 18 §4: widened from SUPER_ADMIN-only — gatc_directory() already calls
# scope_organizations(select(...), actor), which already has a STATE_ADMIN branch restricting to
# the caller's own state_code. Spec 21 §4: widened again to DISTRICT_ADMIN for the same reason —
# scope_organizations() already has that branch too (state AND district). Zero service changes
# needed for this one (unlike users/audit-logs below, which have no scope_* floor of their own).
Admin = Annotated[User, Depends(require_roles(*ADMIN_ROLES))]


# Spec 17 D3: the only directory this step builds. `type` is required — anything but "GATC"
# is 422, not a 404 or an empty page, since no other directory exists yet to return.
@router.get("")
def list_organizations(
    actor: Admin,
    db: DB,
    paging: Annotated[PageParams, Depends()],
    type: Literal["GATC"],
    state_code: Annotated[str | None, Query(max_length=2)] = None,
    district_code: Annotated[str | None, Query(max_length=4)] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
) -> Page[GatcDirectoryOut]:
    orgs, counts, users_by_org, cat_names, has_active, total = org_service.gatc_directory(
        db,
        actor,
        state_code=state_code,
        district_code=district_code,
        q=q.strip() if q else None,
        is_active=is_active,
        limit=paging.page_size,
        offset=paging.offset,
    )
    items = [
        GatcDirectoryOut(
            id=o.id,
            name=o.name,
            state_code=o.state_code,
            district_code=o.district_code,
            eligible_categories=[
                cat_names[c] for c in (o.gatc_eligible_category_ids or []) if c in cat_names
            ],
            pending_cases=counts.get(o.id, (0, 0))[0],
            completed_cases=counts.get(o.id, (0, 0))[1],
            active=has_active.get(o.id, False),
            users=[GatcDirectoryUserOut.from_user(u) for u in users_by_org.get(o.id, [])],
        )
        for o in orgs
    ]
    return Page(items=items, total=total, page=paging.page, page_size=paging.page_size)
