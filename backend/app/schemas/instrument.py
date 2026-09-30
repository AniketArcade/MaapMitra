import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Self

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
from app.models.instrument_category import InstrumentCategory
from app.models.user import User
from app.schemas.common import DistrictCode, Serial, StateCode, StrictModel, Text100, Text500
from app.schemas.instrument_category import InstrumentCategoryOut


def _six_places(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)  # phone GPS gives more


Capacity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
Latitude = Annotated[Decimal, Field(ge=-90, le=90), AfterValidator(_six_places)]
Longitude = Annotated[Decimal, Field(ge=-180, le=180), AfterValidator(_six_places)]

# Spec 16: category_id/category_values are a paired nullable field (both null, or both set) —
# see _category_pair_valid below — so both must be in NULLABLE_FIELDS for InstrumentUpdate to
# allow an explicit `null` on either (clearing the category assignment entirely).
NULLABLE_FIELDS = frozenset(
    {"accuracy_class", "latitude", "longitude", "category_id", "category_values"}
)


def _category_pair_valid(category_id: int | None, category_values: dict[str, Any] | None) -> bool:
    return (category_id is None) == (category_values is None)


CATEGORY_PAIR_ERROR = "category_id and category_values must both be set, or both be omitted/null"


class InstrumentCreate(StrictModel):
    instrument_type: InstrumentType
    manufacturer: Text100
    model: Text100
    serial_number: Serial
    capacity: Capacity
    capacity_unit: CapacityUnit
    accuracy_class: AccuracyClass | None = None
    # Spec 14: "Can the instrument be transported?" Defaults true (office/test-centre) when the
    # caller omits it, matching the DB's own server_default.
    transportable: bool = True
    # Spec 16: the richer, data-driven category system — additive and optional, sitting alongside
    # instrument_type/capacity/capacity_unit/accuracy_class above rather than replacing them.
    # Providing one requires the other (see _category_pair_valid); omitting both is the default
    # ("no category assigned yet", the only state every pre-spec-16 instrument can ever be in).
    category_id: int | None = None
    category_values: dict[str, Any] | None = None
    address: Text500
    state_code: StateCode | None = None  # default: the caller's organization
    district_code: DistrictCode | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None

    @model_validator(mode="after")
    def category_pair_valid(self) -> Self:
        if not _category_pair_valid(self.category_id, self.category_values):
            raise ValueError(CATEGORY_PAIR_ERROR)
        return self


class InstrumentUpdate(StrictModel):
    """PATCH: only sent fields change. instrument_type is not editable (-> 422 as unknown)."""

    manufacturer: Text100 | None = None
    model: Text100 | None = None
    serial_number: Serial | None = None
    capacity: Capacity | None = None
    capacity_unit: CapacityUnit | None = None
    accuracy_class: AccuracyClass | None = None
    transportable: bool | None = None
    category_id: int | None = None
    category_values: dict[str, Any] | None = None
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

    @model_validator(mode="after")
    def category_fields_sent_together(self) -> Self:
        # Spec 16: category_id/category_values must be PATCHed together, in the same request —
        # never one without the other. This mirrors InstrumentCreate's own pairing rule and avoids
        # an ambiguous partial change (e.g. "just swap the category but keep the old values",
        # which could silently leave stale/mismatched values against the new category's schema).
        sent = self.model_fields_set
        id_sent = "category_id" in sent
        values_sent = "category_values" in sent
        if id_sent != values_sent:
            raise ValueError("category_id and category_values must be provided together")
        if id_sent and not _category_pair_valid(self.category_id, self.category_values):
            raise ValueError(CATEGORY_PAIR_ERROR)
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
    transportable: bool
    category_id: int | None
    category_values: dict[str, Any] | None
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
            transportable=i.transportable,
            category_id=i.category_id,
            category_values=i.category_values,
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
    # Spec 16: read from the `instrument_categories` table (not a Python constant like `types`/
    # `regions` above) — the whole point of a real table over an in-memory dict is that the
    # category content can be reviewed/edited as data without a code deploy. build() below takes
    # the rows as a parameter so the router owns the one DB query (this schema module stays
    # DB-session-free, matching every other schema in this file).
    categories: list[InstrumentCategoryOut]

    @classmethod
    def build(cls, categories: list[InstrumentCategory]) -> Self:
        return cls(
            types=[
                TypeMeta(value=t, label=TYPE_LABELS[t], units=list(UNIT_FAMILY[t]))
                for t in InstrumentType
            ],
            accuracy_classes=list(AccuracyClass),
            categories=[InstrumentCategoryOut.from_model(c) for c in categories],
            regions=[
                RegionMeta(
                    state_code=code,
                    state_name=state["name"],
                    districts=[DistrictMeta(code=c, name=n) for c, n in state["districts"].items()],
                )
                for code, state in REGIONS.items()
            ],
        )
