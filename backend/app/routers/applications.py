import uuid
from typing import Annotated

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
    ApplicationUpdate,
    StatusChange,
)
from app.schemas.common import Page, PageParams
from app.services import applications as service

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


def _detail(db: DB, user: User, application_id: uuid.UUID) -> ApplicationDetail:
    application = service.load(db, user, application_id, detail=True)
    return ApplicationDetail.build(application, service.allowed_actions(application, user))


# Declared before /{application_id} so "meta" is never parsed as an id.
@router.get("/meta")
def meta(_: CurrentUser) -> ApplicationMeta:
    return ApplicationMeta.build()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_application(
    request: Request, body: ApplicationCreate, user: Owner, db: DB
) -> ApplicationOut:
    return ApplicationOut.from_model(service.create(db, user, body, ip=get_client_ip(request)))


@router.get("")
def list_applications(
    user: Reader,
    db: DB,
    paging: Annotated[PageParams, Depends()],
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[ApplicationStatus | None, Query(alias="status")] = None,
    instrument_id: uuid.UUID | None = None,
) -> Page[ApplicationOut]:
    items, total = service.list_applications(
        db,
        user,
        q=q.strip() if q else None,
        status=status_filter,
        instrument_id=instrument_id,
        limit=paging.page_size,
        offset=paging.offset,
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
