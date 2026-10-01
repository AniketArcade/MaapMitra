from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DB, require_roles
from app.core.roles import ADMIN_ROLES, Role
from app.models.user import User
from app.schemas.admin import AdminCertificateStats, DistrictOverviewRow, StateOverviewRow
from app.schemas.certificate import CertificateOut
from app.schemas.common import Page, PageParams
from app.services import admin as service

router = APIRouter(prefix="/admin", tags=["admin"])

Admin = Annotated[User, Depends(require_roles(*ADMIN_ROLES))]
# Spec 19 §4: widened for the two certificate-monitoring endpoints only — a new, separate
# dependency, not a change to ADMIN_ROLES itself (that constant also gates GET /api/users,
# /api/audit-logs, /api/organizations?type=GATC, state/district-overview, none of which
# LM_OFFICER should gain). scope_certificates() already resolves correctly for LM_OFFICER via
# scope_applications()'s existing branch — zero service-layer change needed.
AdminOrOfficer = Annotated[User, Depends(require_roles(*ADMIN_ROLES, Role.LM_OFFICER))]


@router.get("/certificates/stats")
def get_certificate_stats(user: AdminOrOfficer, db: DB) -> AdminCertificateStats:
    by_status, expiring_soon = service.certificate_stats(db, user)
    return AdminCertificateStats.from_counts(by_status, expiring_soon)


@router.get("/certificates/expiring-soon")
def list_expiring_soon(
    user: AdminOrOfficer, db: DB, paging: Annotated[PageParams, Depends()]
) -> Page[CertificateOut]:
    items, total = service.expiring_soon(db, user, limit=paging.page_size, offset=paging.offset)
    return Page(
        items=[CertificateOut.from_model(c) for c in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


# Spec 17 §6.4: Super Admin dashboard's state-wise table (the Phase 1 substitute for a map).
# Bounded to len(REGIONS) rows (~36) always — never paginated, that would be decoration.
@router.get("/state-overview")
def get_state_overview(user: Admin, db: DB) -> list[StateOverviewRow]:
    return service.state_overview(db, user)


# Spec 18 §4: State Admin dashboard's district-wise table, one state at a time. For
# STATE_ADMIN/DISTRICT_ADMIN, state_code is forced server-side to the caller's own state
# regardless of what's passed here; SUPER_ADMIN must supply one to drill into a state from the
# state-overview table above.
@router.get("/district-overview")
def get_district_overview(
    user: Admin, db: DB, state_code: Annotated[str | None, Query(max_length=2)] = None
) -> list[DistrictOverviewRow]:
    return service.district_overview(db, user, state_code=state_code)
