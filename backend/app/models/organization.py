from sqlalchemy import CheckConstraint, Enum, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.roles import OrgType
from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk


class Organization(UUIDPk, Timestamps, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("state_code ~ '^[A-Z]{2}$'", name="state_code_format"),
        CheckConstraint("district_code ~ '^[A-Z]{2,4}$'", name="district_code_format"),
        # Spec 15: gatc_eligible_category_ids is only meaningful for a GATC organization — a
        # BUSINESS org that somehow got a value here would be a data bug, not a valid state.
        CheckConstraint(
            "gatc_eligible_category_ids IS NULL OR type = 'GATC'",
            name="gatc_eligible_only_for_gatc_org",
        ),
    )

    type: Mapped[OrgType] = mapped_column(Enum(OrgType, name="org_type"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # ASSUMPTION: generic business registration ID (GSTIN or similar).
    registration_number: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    state_code: Mapped[str] = mapped_column(Text, nullable=False)
    district_code: Mapped[str] = mapped_column(Text, nullable=False)
    # Spec 15: nullable JSONB array of `instrument_categories.id` values, meaningful only for
    # type=GATC organizations (enforced above). No FK to instrument_categories (a JSONB array
    # element can't carry one) and no admin endpoint writes this in this step (see spec 15 §9) —
    # configured directly in the database until a future org-management step adds one. NULL means
    # "not configured for any category" (an ordinary GATC org that hasn't opted in yet), not
    # the same as an empty list (explicitly configured for zero categories); both behave
    # identically in `gatc/eligible` queries (neither ever matches a category_id).
    # none_as_null=True: without it, SQLAlchemy's JSON/JSONB type writes a Python None as the
    # JSON literal 'null'::jsonb, not SQL NULL — indistinguishable from "IS NULL" everywhere
    # except an actual `IS NULL` check, which both the CHECK constraint above and
    # services/gatc.py: list_eligible()'s own query rely on. With this flag, an unset value is a
    # real SQL NULL, matching the "NULL means unconfigured" semantics documented above.
    gatc_eligible_category_ids: Mapped[list[int] | None] = mapped_column(JSONB(none_as_null=True))
