import uuid
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import set_committed_value

from app.core.application_types import ApplicationStatus
from app.core.errors import Conflict, NotFound, Unprocessable
from app.core.instrument_lock import IDENTITY_LOCKED, LOCATION_LOCK_MESSAGE, locked_fields
from app.core.instrument_types import TYPE_LABELS, UNIT_FAMILY, CapacityUnit, InstrumentType
from app.core.regions import is_valid_region, is_valid_state
from app.models.instrument import MFR_SERIAL_INDEX, Instrument, instrument_uid_seq
from app.models.user import User
from app.schemas.instrument import InstrumentCreate, InstrumentUpdate
from app.services import audit
from app.services.scoping import scope_instruments

HAS_APPLICATIONS = "This instrument has applications and can't be deleted"

DUPLICATE = (
    "An instrument with this manufacturer and serial number is already registered. "
    "Contact your district office if you believe this is an error."
)


def _validate(
    *,
    instrument_type: InstrumentType,
    capacity_unit: CapacityUnit,
    latitude: Decimal | None,
    longitude: Decimal | None,
    state_code: str,
    district_code: str,
) -> None:
    """Cross-field rules, checked on the merged state for both create and PATCH."""
    if capacity_unit not in UNIT_FAMILY[instrument_type]:
        label = TYPE_LABELS[instrument_type].lower()
        raise Unprocessable(
            f"'{capacity_unit}' is not a valid unit for a {label}", field="capacity_unit"
        )
    if latitude is None and longitude is not None:
        raise Unprocessable("Provide both latitude and longitude, or neither", field="latitude")
    if longitude is None and latitude is not None:
        raise Unprocessable("Provide both latitude and longitude, or neither", field="longitude")
    if not is_valid_state(state_code):
        raise Unprocessable("Unknown state", field="state_code")
    if not is_valid_region(state_code, district_code):
        raise Unprocessable("Unknown district for this state", field="district_code")


def _flush_or_conflict(db: Session) -> None:
    """The unique index is the duplicate check (no pre-select), so races are covered too."""
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == MFR_SERIAL_INDEX:
            raise Conflict(DUPLICATE) from exc
        raise


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    return value


def _scoped(user: User) -> Select[tuple[Instrument]]:
    stmt = select(Instrument).options(
        joinedload(Instrument.organization), joinedload(Instrument.active_application)
    )
    return scope_instruments(stmt, user)


def create(db: Session, user: User, body: InstrumentCreate, *, ip: str) -> Instrument:
    org = user.organization
    assert org is not None  # BUSINESS users always have an organization (DB constraint)
    state = body.state_code or org.state_code
    district = body.district_code or org.district_code
    _validate(
        instrument_type=body.instrument_type,
        capacity_unit=body.capacity_unit,
        latitude=body.latitude,
        longitude=body.longitude,
        state_code=state,
        district_code=district,
    )

    seq = db.scalar(select(instrument_uid_seq.next_value()))
    instrument = Instrument(
        **body.model_dump(exclude={"state_code", "district_code"}),
        state_code=state,
        district_code=district,
        instrument_uid=f"LM-{state}-{district}-{seq:06d}",
        organization=org,
        created_by=user.id,
    )
    db.add(instrument)
    _flush_or_conflict(db)

    audit.log(
        db,
        actor=user,
        action="INSTRUMENT_CREATED",
        entity_type="instrument",
        entity_id=instrument.id,
        organization_id=org.id,
        details={
            "instrument_uid": instrument.instrument_uid,
            "serial_number": instrument.serial_number,
        },
        ip=ip,
    )
    db.commit()
    set_committed_value(instrument, "active_application", None)  # brand new: none yet
    return instrument


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_instruments(
    db: Session,
    user: User,
    *,
    q: str | None,
    instrument_type: InstrumentType | None,
    state_code: str | None,
    district_code: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Instrument], int]:
    stmt = scope_instruments(select(Instrument), user)
    if q:
        pattern = f"%{_escape_like(q)}%"
        stmt = stmt.where(
            or_(
                *(
                    col.ilike(pattern, escape="\\")
                    for col in (
                        Instrument.instrument_uid,
                        Instrument.serial_number,
                        Instrument.manufacturer,
                        Instrument.model,
                    )
                )
            )
        )
    if instrument_type:
        stmt = stmt.where(Instrument.instrument_type == instrument_type)
    if state_code:  # only narrows further inside the caller's scope
        stmt = stmt.where(Instrument.state_code == state_code)
    if district_code:
        stmt = stmt.where(Instrument.district_code == district_code)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.options(joinedload(Instrument.organization), joinedload(Instrument.active_application))
        .order_by(Instrument.created_at.desc(), Instrument.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total


def get(
    db: Session, user: User, instrument_id: uuid.UUID, *, for_update: bool = False
) -> Instrument:
    """One scoped query: missing and out-of-scope are indistinguishable (404)."""
    stmt = _scoped(user).where(Instrument.id == instrument_id)
    if for_update:
        stmt = stmt.with_for_update(of=Instrument).execution_options(populate_existing=True)
    instrument = db.scalar(stmt)
    if instrument is None:
        raise NotFound("Instrument not found")
    return instrument


def update(
    db: Session, user: User, instrument_id: uuid.UUID, body: InstrumentUpdate, *, ip: str
) -> Instrument:
    instrument = get(db, user, instrument_id, for_update=True)
    sent = body.model_dump(exclude_unset=True)
    changes = {
        field: (getattr(instrument, field), value)
        for field, value in sent.items()
        if getattr(instrument, field) != value
    }
    if not changes:
        db.commit()  # releases the row lock; no UPDATE is issued, so updated_at is unchanged
        return instrument

    active = instrument.active_application
    locked = locked_fields(active.status if active is not None else None)
    touched = changes.keys() & locked
    if touched:
        if touched & IDENTITY_LOCKED:
            message = (
                "This instrument has an application in progress; these details can't be changed."
            )
            if active is not None and active.status == ApplicationStatus.DRAFT:
                message += " Delete the draft to edit them."
        else:
            message = LOCATION_LOCK_MESSAGE
        raise Conflict(message)

    merged = {
        field: sent.get(field, getattr(instrument, field))
        for field in ("capacity_unit", "latitude", "longitude", "state_code", "district_code")
    }
    _validate(instrument_type=instrument.instrument_type, **merged)

    for field, (_, new) in changes.items():
        setattr(instrument, field, new)
    _flush_or_conflict(db)
    audit.log(
        db,
        actor=user,
        action="INSTRUMENT_UPDATED",
        entity_type="instrument",
        entity_id=instrument.id,
        organization_id=instrument.organization_id,
        details={"changes": {f: [_jsonable(o), _jsonable(n)] for f, (o, n) in changes.items()}},
        ip=ip,
    )
    db.commit()
    db.refresh(instrument, ["updated_at"])
    return instrument


def delete(db: Session, user: User, instrument_id: uuid.UUID, *, ip: str) -> None:
    instrument = get(db, user, instrument_id, for_update=True)
    audit.log(
        db,
        actor=user,
        action="INSTRUMENT_DELETED",
        entity_type="instrument",
        entity_id=instrument.id,
        organization_id=instrument.organization_id,
        details={
            "instrument_uid": instrument.instrument_uid,
            "serial_number": instrument.serial_number,
        },
        ip=ip,
    )
    db.delete(instrument)
    try:
        db.flush()  # the RESTRICT foreign key from applications fires here
    except IntegrityError as exc:
        db.rollback()
        raise Conflict(HAS_APPLICATIONS) from exc
    db.commit()
