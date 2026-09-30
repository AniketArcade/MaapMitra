"""Instrument categories — spec 16 (`docs/specs/16-instrument-categories.md`).

ASSUMPTION: ported wholesale from a separate prototype repo's own mock fixture data
(`MaapMitrafrontend/src/data/instrumentCategories.ts`), which that repo's own
`docs/SPEC.md` §15 already flags as "invented-but-realistic, loosely modeled on Indian
Legal Metrology (Legal Metrology Act 2009 / General Rules 2011) verification categories
... not sourced from an actual regulation." That caveat carries over unchanged here — the
33 rows below are NOT sourced from the real Legal Metrology Act 2009 or its rules, and per
the task that introduced this table, the migration seeding them must **not** be applied to
the real Supabase database until a human has reviewed the category content.

A small, fixed (1-33), rarely-changing reference/taxonomy set — like `core/regions.py`'s
`REGIONS` dict, but promoted to a real table (rather than an in-memory Python dict) so it
ships with the schema in every environment (including a future Supabase apply) and can be
read by `GET /instruments/meta` without the frontend ever importing a static list. Unlike
`REGIONS`, this needs a real column of nested JSON per row, and unlike `InstrumentType`/
`CapacityUnit`/`AccuracyClass` (fixed enums with no per-value structure beyond a label),
each row needs a rich JSON field-schema — a Postgres enum can't hold that.

`id` is a smallint primary key, not the codebase's usual `UUIDPk` mixin: these are a small,
fixed, numbered reference set (1-33, matching the donor prototype's own stable category
numbers, referenced by number in that repo's CLAUDE.md §8 for special-case behaviors like
"+ Add Weight" / "+ Add Nozzle" / "+ Add Compartment"), not user-generated rows. A UUID
would only obscure that fixed numbering for no benefit.
"""

from typing import Any

from sqlalchemy import SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import Timestamps


class InstrumentCategory(Timestamps, Base):
    __tablename__ = "instrument_categories"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    validity_months: Mapped[int] = mapped_column(nullable=False)
    # Array of field definitions — same shape as the donor's `CategoryField[]`, translated to
    # snake_case JSON keys (see schemas/instrument_category.py: CategoryFieldSchema for the exact
    # shape). A JSONB blob, not relational rows: this is read whole on every use (rendering a
    # dynamic form, or checking required-field presence), never queried/filtered by sub-field —
    # the same "one immutable bundle" reasoning `certificates.snapshot` already documents for
    # itself, though this one is admin-authored and category-scoped rather than issuance-time and
    # per-application.
    field_schema: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
