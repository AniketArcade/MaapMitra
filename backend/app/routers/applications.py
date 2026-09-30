import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, status

from app.core.application_types import ApplicationStatus
from app.core.deps import DB, CurrentUser, get_client_ip, require_roles
from app.core.roles import Role
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationMeta,
    ApplicationOut,
    ApplicationStats,
    ApplicationUpdate,
    InspectionReschedule,
    ReviewChecklistUpdate,
    StatusChange,
)
from app.schemas.common import Page, PageParams
from app.services import applications as service
from app.services import certificates as certificates_service
from app.services import inspections as inspections_service
from app.services import payments as payments_service

router = APIRouter(prefix="/applications", tags=["applications"])

Reader = Annotated[
    User,
    Depends(
        require_roles(
            Role.BUSINESS, Role.LM_OFFICER, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN
        )
    ),
]
Owner = Annotated[User, Depends(require_roles(Role.BUSINESS))]
Officer = Annotated[User, Depends(require_roles(Role.LM_OFFICER))]


def _detail(db: DB, user: User, application_id: uuid.UUID) -> ApplicationDetail:
    application = service.load(db, user, application_id, detail=True)
    summary = None
    if application.inspection and application.inspection.submitted_at is not None:
        summary = inspections_service.checklist_summary(db, application.inspection.id)
    review_checklist = service.review_checklist_items(db, application.id)
    return ApplicationDetail.build(
        application,
        user,
        service.allowed_actions(application, user),
        checklist_summary=summary,
        review_checklist=review_checklist,
    )


# Declared before /{application_id} so "meta" is never parsed as an id.
@router.get("/meta")
def meta(_: CurrentUser) -> ApplicationMeta:
    return ApplicationMeta.build()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_application(
    request: Request, body: ApplicationCreate, user: Owner, db: DB
) -> ApplicationOut:
    return ApplicationOut.from_model(service.create(db, user, body, ip=get_client_ip(request)))


# Declared before /{application_id} so "stats" is never parsed as an id.
@router.get("/stats")
def get_stats(user: Reader, db: DB) -> ApplicationStats:
    return ApplicationStats.from_counts(service.stats(db, user))


@router.get("")
def list_applications(
    user: Reader,
    db: DB,
    paging: Annotated[PageParams, Depends()],
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[ApplicationStatus | None, Query(alias="status")] = None,
    instrument_id: uuid.UUID | None = None,
    sort: Literal["created_desc", "scheduled_asc"] = "created_desc",
) -> Page[ApplicationOut]:
    items, total = service.list_applications(
        db,
        user,
        q=q.strip() if q else None,
        status=status_filter,
        instrument_id=instrument_id,
        limit=paging.page_size,
        offset=paging.offset,
        sort=sort,
    )
    return Page(
        items=[ApplicationOut.from_model(a) for a in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get("/{application_id}")
def get_application(application_id: uuid.UUID, user: Reader, db: DB) -> ApplicationDetail:
    return _detail(db, user, application_id)


@router.patch("/{application_id}")
def update_application(
    request: Request, application_id: uuid.UUID, body: ApplicationUpdate, user: Owner, db: DB
) -> ApplicationOut:
    application = service.update(db, user, application_id, body, ip=get_client_ip(request))
    return ApplicationOut.from_model(application)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(request: Request, application_id: uuid.UUID, user: Owner, db: DB) -> None:
    service.delete(db, user, application_id, ip=get_client_ip(request))


@router.patch("/{application_id}/status")
def change_status(
    request: Request, application_id: uuid.UUID, body: StatusChange, user: Reader, db: DB
) -> ApplicationDetail:
    service.transition(db, user, application_id, body, ip=get_client_ip(request))
    return _detail(db, user, application_id)


@router.patch("/{application_id}/review-checklist")
def patch_review_checklist(
    request: Request,
    application_id: uuid.UUID,
    body: ReviewChecklistUpdate,
    user: Officer,
    db: DB,
) -> ApplicationDetail:
    service.patch_review_checklist(db, user, application_id, body, ip=get_client_ip(request))
    return _detail(db, user, application_id)


@router.patch("/{application_id}/inspection")
def reschedule_inspection(
    request: Request,
    application_id: uuid.UUID,
    body: InspectionReschedule,
    user: Officer,
    db: DB,
) -> ApplicationDetail:
    service.reschedule(db, user, application_id, body, ip=get_client_ip(request))
    return _detail(db, user, application_id)


@router.post("/{application_id}/certificate")
def issue_certificate(
    request: Request, application_id: uuid.UUID, user: Officer, db: DB
) -> ApplicationDetail:
    certificates_service.issue(db, user, application_id, ip=get_client_ip(request))
    return _detail(db, user, application_id)


@router.post("/{application_id}/mock-pay")
def mock_pay(request: Request, application_id: uuid.UUID, user: Owner, db: DB) -> ApplicationDetail:
    """Spec 12: mocked, informational-only payment action. BUSINESS (owner) only — out-of-org is
    404 via applications_service.load(), never 403, same as every other Owner-gated endpoint."""
    payments_service.mock_pay(db, user, application_id, ip=get_client_ip(request))
    return _detail(db, user, application_id)
