import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Self

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.core.application_types import ApplicationStatus
from app.core.instrument_lock import locked_fields
from app.core.instrument_types import (
    TYPE_LABELS,
    UNIT_FAMILY,
    AccuracyClass,
    CapacityUnit,
    InstrumentType,
)
from app.core.regions import REGIONS
from app.core.roles import Role
from app.models.instrument import Instrument
from app.models.user import User
from app.schemas.common import DistrictCode, Serial, StateCode, StrictModel, Text100, Text500


def _six_places(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)  # phone GPS gives more


Capacity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
Latitude = Annotated[Decimal, Field(ge=-90, le=90), AfterValidator(_six_places)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180), AfterValidator(_six_places)]

NULLABLE_FIELDS = frozenset({"accuracy_class", "latitude", "longitude"})


class InstrumentCreate(StrictModel):
    instrument_type: InstrumentType
    manufacturer: Text100
    model: Text100
    serial_number: Serial
    capacity: Capacity
    capacity_unit: CapacityUnit
    accuracy_class: AccuracyClass | None = None
    address: Text500
    state_code: StateCode | None = None  # default: the caller's organization
    district_code: DistrictCode | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None


class InstrumentUpdate(StrictModel):
    """PATCH: only sent fields change. instrument_type is not editable (-> 422 as unknown)."""

    manufacturer: Text100 | None = None
    model: Text100 | None = None
    serial_number: Serial | None = None
    capacity: Capacity | None = None
    capacity_unit: CapacityUnit | None = None
    accuracy_class: AccuracyClass | None = None
    address: Text500 | None = None
    state_code: StateCode | None = None
    district_code: DistrictCode | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None

    @model_validator(mode="after")
    def reject_null_for_required(self) -> Self:
        for name in self.model_fields_set - NULLABLE_FIELDS:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ActiveApplicationRef(BaseModel):
    id: uuid.UUID
    application_number: str
    status: ApplicationStatus


class InstrumentOut(BaseModel):
    id: uuid.UUID
    instrument_uid: str
    organization_id: uuid.UUID
    organization_name: str
    instrument_type: InstrumentType
    manufacturer: str
    model: str
    serial_number: str
    capacity: float
    capacity_unit: CapacityUnit
    accuracy_class: AccuracyClass | None
    address: str
    state_code: str
    district_code: str
    latitude: float | None
    longitude: float | None
    created_at: datetime
    updated_at: datetime
    active_application: ActiveApplicationRef | None = None
    locked_fields: list[str]

    @classmethod
    def from_model(cls, i: Instrument, viewer: User | None = None) -> Self:
        # Unfiltered: locking is a business-only concern (only BUSINESS can PATCH), independent
        # of the officials-never-see-DRAFT display rule below.
        raw_active = i.active_application
        active = raw_active
        # Officials never see drafts (spec 03 §4), so a draft is reported as "none".
        if (
            active is not None
            and active.status == ApplicationStatus.DRAFT
            and (viewer is None or viewer.role != Role.BUSINESS)
        ):
            active = None
        return cls(
            id=i.id,
            instrument_uid=i.instrument_uid,
            organization_id=i.organization_id,
            organization_name=i.organization.name,
            instrument_type=i.instrument_type,
            manufacturer=i.manufacturer,
            model=i.model,
            serial_number=i.serial_number,
            capacity=float(i.capacity),
            capacity_unit=i.capacity_unit,
            accuracy_class=i.accuracy_class,
            address=i.address,
            state_code=i.state_code,
            district_code=i.district_code,
            latitude=float(i.latitude) if i.latitude is not None else None,
            longitude=float(i.longitude) if i.longitude is not None else None,
            created_at=i.created_at,
            updated_at=i.updated_at,
            locked_fields=sorted(locked_fields(raw_active.status if raw_active else None)),
            active_application=(
                ActiveApplicationRef(
                    id=active.id,
                    application_number=active.application_number,
                    status=active.status,
                )
                if active is not None
                else None
            ),
        )


class TypeMeta(BaseModel):
    value: InstrumentType
    label: str
    units: list[CapacityUnit]


class DistrictMeta(BaseModel):
    code: str
    name: str


class RegionMeta(BaseModel):
    state_code: str
    state_name: str
    districts: list[DistrictMeta]


class InstrumentMeta(BaseModel):
    types: list[TypeMeta]
    accuracy_classes: list[AccuracyClass]
    regions: list[RegionMeta]

    @classmethod
    def build(cls) -> Self:
        return cls(
            types=[
                TypeMeta(value=t, label=TYPE_LABELS[t], units=list(UNIT_FAMILY[t]))
                for t in InstrumentType
            ],
            accuracy_classes=list(AccuracyClass),
            regions=[
                RegionMeta(
                    state_code=code,
                    state_name=state["name"],
                    districts=[DistrictMeta(code=c, name=n) for c, n in state["districts"].items()],
                )
                for code, state in REGIONS.items()
            ],
        )
