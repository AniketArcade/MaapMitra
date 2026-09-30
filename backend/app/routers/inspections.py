import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.deps import DB, CurrentUser, get_client_ip
from app.core.errors import Forbidden
from app.core.roles import Role
from app.models.user import User
from app.schemas.inspection import InspectionDetail, InspectionMeta, InspectionUpdate
from app.services import gatc as gatc_service
from app.services import inspections as service

router = APIRouter(prefix="/inspections", tags=["inspections"])

READER_ROLES = frozenset(
    {Role.BUSINESS, Role.LM_OFFICER, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN}
)


def _reader_or_assigned_gatc(inspection_id: uuid.UUID, user: CurrentUser, db: DB) -> User:
    """Spec 15: same reasoning as routers/applications.py's own _reader_or_assigned_gatc — GATC
    stays blanket-403 (never 404) for any inspection it isn't the assignee of, preserving every
    pre-existing RBAC test; the assigned GATC user is admitted, exactly like LM_OFFICER already
    is unconditionally at this router level (the service layer does the fine-grained "must be
    THIS assigned officer" check for both roles identically, e.g. patch()/submit()'s
    _require_assigned_officer_not_submitted)."""
    if user.role in READER_ROLES:
        return user
    if user.role == Role.GATC and gatc_service.is_assigned_gatc_for_inspection(
        db, inspection_id=inspection_id, user_id=user.id
    ):
        return user
    raise Forbidden("Insufficient permissions")


def _officer_or_assigned_gatc(inspection_id: uuid.UUID, user: CurrentUser, db: DB) -> User:
    """Spec 15: PATCH/submit remain LM_OFFICER-or-assigned-GATC only — any LM_OFFICER may reach
    the service (which then enforces "must be the assigned officer specifically", spec 06 D1,
    role-agnostic already); a GATC caller must already be that specific assignee to pass this
    router gate at all, since GATC has no jurisdiction-wide equivalent of "any LM_OFFICER"."""
    if user.role == Role.LM_OFFICER:
        return user
    if user.role == Role.GATC and gatc_service.is_assigned_gatc_for_inspection(
        db, inspection_id=inspection_id, user_id=user.id
    ):
        return user
    raise Forbidden("Insufficient permissions")


Reader = Annotated[User, Depends(_reader_or_assigned_gatc)]
Officer = Annotated[User, Depends(_officer_or_assigned_gatc)]


# Declared before /{inspection_id} so "meta" is never parsed as an id.
@router.get("/meta")
def meta(_: CurrentUser) -> InspectionMeta:
    return InspectionMeta.build()


@router.get("/{inspection_id}")
def get_inspection(inspection_id: uuid.UUID, user: Reader, db: DB) -> InspectionDetail:
    return service.detail(db, user, inspection_id)


@router.patch("/{inspection_id}")
def patch_inspection(
    inspection_id: uuid.UUID, body: InspectionUpdate, user: Officer, db: DB
) -> InspectionDetail:
    return service.patch(db, user, inspection_id, body)


@router.post("/{inspection_id}/submit")
def submit_inspection(
    request: Request, inspection_id: uuid.UUID, user: Officer, db: DB
) -> InspectionDetail:
    return service.submit(db, user, inspection_id, ip=get_client_ip(request))
