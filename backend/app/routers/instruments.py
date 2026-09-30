import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select

from app.core.deps import DB, CurrentUser, get_client_ip, require_roles
from app.core.instrument_types import InstrumentType
from app.core.roles import Role
from app.models.instrument_category import InstrumentCategory
from app.models.user import User
from app.schemas.common import Page, PageParams
from app.schemas.instrument import InstrumentCreate, InstrumentMeta, InstrumentOut, InstrumentUpdate
from app.services import instruments as service

router = APIRouter(prefix="/instruments", tags=["instruments"])

Reader = Annotated[
    User,
    Depends(
        require_roles(
            Role.BUSINESS, Role.LM_OFFICER, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN
        )
    ),
]
Owner = Annotated[User, Depends(require_roles(Role.BUSINESS))]


# Declared before /{instrument_id} so "meta" is never parsed as an id.
@router.get("/meta")
def meta(_: CurrentUser, db: DB) -> InstrumentMeta:
    categories = db.scalars(select(InstrumentCategory).order_by(InstrumentCategory.id)).all()
    return InstrumentMeta.build(list(categories))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_instrument(
    request: Request, body: InstrumentCreate, user: Owner, db: DB
) -> InstrumentOut:
    instrument = service.create(db, user, body, ip=get_client_ip(request))
    return InstrumentOut.from_model(instrument, user)


@router.get("")
def list_instruments(
    user: Reader,
    db: DB,
    paging: Annotated[PageParams, Depends()],
    q: Annotated[str | None, Query(max_length=100)] = None,
    instrument_type: InstrumentType | None = None,
    state_code: Annotated[str | None, Query(max_length=2)] = None,
    district_code: Annotated[str | None, Query(max_length=4)] = None,
) -> Page[InstrumentOut]:
    items, total = service.list_instruments(
        db,
        user,
        q=q.strip() if q else None,
        instrument_type=instrument_type,
        state_code=state_code.upper() if state_code else None,
        district_code=district_code.upper() if district_code else None,
        limit=paging.page_size,
        offset=paging.offset,
    )
    return Page(
        items=[InstrumentOut.from_model(i, user) for i in items],
        total=total,
        page=paging.page,
        page_size=paging.page_size,
    )


@router.get("/{instrument_id}")
def get_instrument(instrument_id: uuid.UUID, user: Reader, db: DB) -> InstrumentOut:
    return InstrumentOut.from_model(service.get(db, user, instrument_id), user)


@router.patch("/{instrument_id}")
def update_instrument(
    request: Request, instrument_id: uuid.UUID, body: InstrumentUpdate, user: Owner, db: DB
) -> InstrumentOut:
    instrument = service.update(db, user, instrument_id, body, ip=get_client_ip(request))
    return InstrumentOut.from_model(instrument, user)


@router.delete("/{instrument_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_instrument(request: Request, instrument_id: uuid.UUID, user: Owner, db: DB) -> None:
    service.delete(db, user, instrument_id, ip=get_client_ip(request))
