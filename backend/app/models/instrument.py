import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    Sequence,
    SmallInteger,
    Text,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.instrument_types import AccuracyClass, CapacityUnit, InstrumentType
from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk
from app.models.organization import Organization

# Global UID counter. Created by hand in migration 0002 (autogenerate ignores sequences).
instrument_uid_seq = Sequence("instrument_uid_seq", metadata=Base.metadata)

MFR_SERIAL_INDEX = "ix_instruments_mfr_serial"


class Instrument(UUIDPk, Timestamps, Base):
    __tablename__ = "instruments"

    instrument_uid: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    instrument_type: Mapped[InstrumentType] = mapped_column(
        Enum(InstrumentType, name="instrument_type"), nullable=False
    )
    manufacturer: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    serial_number: Mapped[str] = mapped_column(Text, nullable=False)
    capacity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    capacity_unit: Mapped[CapacityUnit] = mapped_column(
        Enum(CapacityUnit, name="capacity_unit"), nullable=False
    )
    accuracy_class: Mapped[AccuracyClass | None] = mapped_column(
        Enum(AccuracyClass, name="accuracy_class")
    )
    # Spec 14: "Can the instrument be transported?" Drives the office/test-centre vs. on-site
    # verification-mode snapshot taken on `Application` at creation (see
    # `app/services/applications.py: create()`). Same server_default(true()) + NOT NULL pattern
    # as `User.is_active`; migration 0009 adds it nullable first, backfills, then sets NOT NULL
    # (see that migration's comment for why).
    transportable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    # Spec 16: additive, opt-in richer category system that sits alongside `instrument_type`
    # (above) rather than replacing it — existing rows keep `category_id = NULL` and keep working
    # entirely off `instrument_type`/`capacity`/`capacity_unit`/`accuracy_class`, never backfilled.
    # `ON DELETE SET NULL` (never CASCADE/RESTRICT): a category row being removed in the future
    # must not delete or block deleting the instruments that reference it — the instrument simply
    # loses its category classification, exactly like an honest "no category assigned" state.
    category_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("instrument_categories.id", ondelete="SET NULL")
    )
    # The filled-in values for `category_id`'s field_schema, keyed by CategoryField.key — mirrors
    # the donor's `Instrument.categoryValues: Record<string, unknown>`. NULL whenever category_id
    # is NULL (enforced by the schema layer, not a DB constraint — see schemas/instrument.py).
    category_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    state_code: Mapped[str] = mapped_column(Text, nullable=False)
    district_code: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # lazy="raise": always joinedload explicitly, so list endpoints can't N+1.
    organization: Mapped[Organization] = relationship(lazy="raise")

    __table_args__ = (
        CheckConstraint("capacity > 0", name="capacity_positive"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="lat_lng_pair"),
        # Hand-written in the migration; autogenerate skips functional indexes.
        Index(MFR_SERIAL_INDEX, func.lower(manufacturer), serial_number, unique=True),
        Index("ix_instruments_org_created", "organization_id", "created_at"),
        Index("ix_instruments_region", "state_code", "district_code"),
    )
