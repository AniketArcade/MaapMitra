import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.core.deps import DB, require_roles
from app.core.errors import NotFound
from app.core.roles import OrgType, Role
from app.models.organization import Organization
from app.models.user import User
from app.schemas.gatc import GatcEligibleOrgOut, GatcOrgUserOut
from app.services import gatc as service
from app.services.scoping import scope_organizations

router = APIRouter(prefix="/gatc", tags=["gatc"])

# Spec 15: only LM_OFFICER can reach this — the sole role that ever schedules an inspection
# (services/applications.py: ALLOWED_TRANSITIONS[(DOCUMENT_REVIEW, SCHEDULED)]). BUSINESS is
# deliberately excluded: a business never chooses how its application is routed (that decision is
# the Controller/officer's, per the domain rules), and this endpoint would otherwise leak an
# operational list of GATC organization names/jurisdictions to an applicant with no action they
# could take on it. Admin roles are excluded too — they don't schedule, and this is a live
# operational lookup tied to the act of scheduling, not a reporting/read surface (those roles
# already get org-level visibility elsewhere, e.g. GET /admin/certificates/*).
Officer = Annotated[User, Depends(require_roles(Role.LM_OFFICER))]


# Declared before /{organization_id}/users: different path shapes ("eligible" is one segment,
# "{organization_id}/users" is two), so there's no real ambiguity either way, but this matches the
# "fixed path before dynamic" convention used elsewhere in this codebase (e.g. /meta, /stats).
@router.get("/eligible")
def eligible(
    category_id: Annotated[int, Query(ge=1, le=33)], user: Officer, db: DB
) -> list[GatcEligibleOrgOut]:
    return [GatcEligibleOrgOut.from_model(o) for o in service.list_eligible(db, user, category_id)]


@router.get("/{organization_id}/users")
def org_users(organization_id: uuid.UUID, user: Officer, db: DB) -> list[GatcOrgUserOut]:
    # A GET-by-id lookup: out-of-scope/unknown/non-GATC org is 404, matching this codebase's own
    # scope_* convention for reads (unlike resolve_gatc_assignment's 422, which validates a
    # reference inside a PATCH body, not a resource load).
    org = db.scalar(
        scope_organizations(select(Organization), user).where(
            Organization.id == organization_id, Organization.type == OrgType.GATC
        )
    )
    if org is None:
        raise NotFound("GATC organization not found")
    return [GatcOrgUserOut.from_model(u) for u in service.list_org_gatc_users(db, user, org.id)]
