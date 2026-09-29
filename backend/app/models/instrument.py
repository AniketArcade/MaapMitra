import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    Sequence,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
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
