from typing import Self

from pydantic import BaseModel

from app.models.instrument_category import InstrumentCategory


class CategoryFieldOption(BaseModel):
    value: str
    label: str


class CategoryFieldSchema(BaseModel):
    """One field definition inside `InstrumentCategory.field_schema` (spec 16).

    Same shape as the donor prototype's `CategoryField` (`MaapMitrafrontend/src/types/domain.ts`),
    translated to snake_case JSON keys for consistency with this codebase's own convention
    (everywhere else in this backend is snake_case; the donor is a separate TypeScript repo using
    camelCase, which does not carry over). `type` is left as a plain `str`, not a Python enum:
    the field-schema values live in DB rows (JSONB), not in code, so the set of valid `type`
    values is documented here (see `type` below) rather than enforced by a Python type — the same
    "trust the seeded content, don't over-model it in Python" posture this table's JSONB column
    already takes for the whole field_schema array.
    """

    key: str
    label: str
    # One of: "text", "number", "select", "multiselect", "unit-number", "range-band", "repeater",
    # "toggle", "date", "file" — the donor's FieldType union, ported as documentation rather than
    # a Python enum (see class docstring).
    type: str
    required: bool = False
    unit: str | None = None
    unit_options: list[str] | None = None
    options: list[CategoryFieldOption] | None = None
    presets: list[CategoryFieldOption] | None = None
    repeater_label: str | None = None
    repeater_fields: list["CategoryFieldSchema"] | None = None
    min: float | None = None
    max: float | None = None
    help_text: str | None = None


CategoryFieldSchema.model_rebuild()


class InstrumentCategoryOut(BaseModel):
    id: int
    name: str
    validity_months: int
    field_schema: list[CategoryFieldSchema]

    @classmethod
    def from_model(cls, c: InstrumentCategory) -> Self:
        return cls(
            id=c.id,
            name=c.name,
            validity_months=c.validity_months,
            field_schema=[CategoryFieldSchema.model_validate(f) for f in c.field_schema],
        )
