from sqlalchemy import CheckConstraint, Enum, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.roles import OrgType
from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk


class Organization(UUIDPk, Timestamps, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("state_code ~ '^[A-Z]{2}$'", name="state_code_format"),
        CheckConstraint("district_code ~ '^[A-Z]{2,4}$'", name="district_code_format"),
    )

    type: Mapped[OrgType] = mapped_column(Enum(OrgType, name="org_type"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # ASSUMPTION: generic business registration ID (GSTIN or similar).
    registration_number: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    state_code: Mapped[str] = mapped_column(Text, nullable=False)
    district_code: Mapped[str] = mapped_column(Text, nullable=False)
