from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import DB, require_roles
from app.core.roles import ADMIN_ROLES
from app.models.user import User
from app.schemas.admin import AdminCertificateStats, StateOverviewRow
from app.schemas.certificate import CertificateOut
from app.schemas.common import Page, PageParams
from app.services import admin as service

router = APIRouter(prefix="/admin", tags=["admin"])

Admin = Annotated[User, Depends(require_roles(*ADMIN_ROLES))]


@router.get("/certificates/stats")
def get_certificate_stats(user: Admin, db: DB) -> AdminCertificateStats:
    by_status, expiring_soon = service.certificate_stats(db, user)
    return AdminCertificateStats.from_counts(by_status, expiring_soon)


@router.get("/certificates/expiring-soon")
def list_expiring_soon(
    user: Admin, db: DB, paging: Annotated[PageParams, Depends()]
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
