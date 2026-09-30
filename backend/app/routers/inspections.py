import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.deps import DB, CurrentUser, get_client_ip, require_roles
from app.core.roles import Role
from app.models.user import User
from app.schemas.inspection import InspectionDetail, InspectionMeta, InspectionUpdate
from app.services import inspections as service

router = APIRouter(prefix="/inspections", tags=["inspections"])

Reader = Annotated[
    User,
    Depends(
        require_roles(
            Role.BUSINESS, Role.LM_OFFICER, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN
        )
    ),
]
Officer = Annotated[User, Depends(require_roles(Role.LM_OFFICER))]


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
