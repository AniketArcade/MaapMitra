"""instrument categories

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-01 00:12:00.000000

Spec 16 (`docs/specs/16-instrument-categories.md`). Adds a new, additive, opt-in richer
instrument-category system alongside the existing `InstrumentType` enum/flat fields — nothing
existing is altered or removed.

**NOT YET APPLIED TO SUPABASE.** This migration's data-seed step inserts 33 category rows ported
from a separate prototype repo's own mock fixture content
(`MaapMitrafrontend/src/data/instrumentCategories.ts`), which that repo's own `docs/SPEC.md` §15
explicitly flags as "invented-but-realistic... not sourced from an actual regulation." The user
must review the seeded category content (names, fields, options, units) before this migration is
ever run against the real Supabase database — see `backend/CLAUDE.md`'s migration table entry for
this revision.

Three things happen here, in one migration/transaction:
1. `CREATE TABLE instrument_categories` (id smallint PK 1-33, name, validity_months, field_schema
   JSONB) — a brand-new table, no new enum type involved (field_schema is JSONB, not an enum).
2. A data-seed step (`op.bulk_insert`) inserting all 33 rows, directly in this migration rather
   than via `app/seed.py`/`database/seed/` — see the "seed-via-migration, not demo-seed" decision
   in `docs/specs/16-instrument-categories.md` §9 D2: this is reference/taxonomy data the app
   needs to function (like `app/core/regions.py`'s REGIONS, but promoted to a real table), not
   demo-only content, so it must not be gated behind `app/seed.py`'s `ENV=production` guard —
   every environment (including a future Supabase apply) needs this table populated for the
   category system to work at all.
3. `ALTER TABLE instruments ADD COLUMN category_id ...` (smallint, FK -> instrument_categories.id,
   ON DELETE SET NULL) and `ADD COLUMN category_values ...` (JSONB, nullable) — both nullable, no
   backfill: every pre-existing instrument row gets category_id/category_values = NULL and keeps
   working entirely off the existing instrument_type/capacity/capacity_unit/accuracy_class fields
   (spec 16 §"out of scope": no attempt to map old rows onto the new 33 categories).

This migration is self-contained: the seed data below is inlined as literal Python data, not
imported from `app/core/...` — migrations must stay frozen/replayable independent of later
application-code changes (per `backend/CLAUDE.md`'s "never edit an already-applied migration"
rule), so this file does not depend on any runtime module that might itself change later.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _opts(*values: str) -> list[dict[str, str]]:
    """Mirrors the donor TS file's own `const opts = (...values) => values.map(v => ({value: v,
    label: v}))` helper, used identically here for the same option lists."""
    return [{"value": v, "label": v} for v in values]


# Ported field-by-field from MaapMitrafrontend/src/data/instrumentCategories.ts. Dict KEYS are
# translated to snake_case (unitOptions -> unit_options, repeaterLabel -> repeater_label,
# repeaterFields -> repeater_fields, helpText -> help_text) per spec 16 §"decisions" (this
# backend's own snake_case convention). Field VALUES (including each field's own `key`, e.g.
# "weightClass", "nominalValue") are preserved byte-for-byte from the donor — those are opaque
# identifiers/labels, not structural JSON keys, and renaming them was never asked for.
SEED_CATEGORIES: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Standard Weights",
        "validity_months": 24,
        "field_schema": [
            {
                "key": "weightClass",
                "label": "Class",
                "type": "select",
                "required": True,
                "options": _opts("M1", "M2", "M3", "E1", "E2", "F1", "F2"),
            },
            {
                "key": "material",
                "label": "Material",
                "type": "select",
                "required": True,
                "options": _opts("Cast Iron", "Stainless Steel", "Brass"),
            },
            {
                "key": "denominations",
                "label": "Denominations",
                "type": "repeater",
                "required": True,
                "repeater_label": "+ Add Weight",
                "repeater_fields": [
                    {
                        "key": "nominalValue",
                        "label": "Nominal value",
                        "type": "unit-number",
                        "unit_options": ["kg", "g"],
                        "required": True,
                    },
                ],
            },
        ],
    },
    {
        "id": 2,
        "name": "Carat / Jewellery Weights",
        "validity_months": 24,
        "field_schema": [
            {
                "key": "weightClass",
                "label": "Class",
                "type": "select",
                "required": True,
                "options": _opts("E1", "E2"),
            },
            {
                "key": "denominations",
                "label": "Denominations",
                "type": "repeater",
                "required": True,
                "repeater_label": "+ Add Weight",
                "repeater_fields": [
                    {
                        "key": "nominalValue",
                        "label": "Nominal value",
                        "type": "unit-number",
                        "unit": "ct",
                        "required": True,
                    },
                ],
            },
            {"key": "setSize", "label": "Set size", "type": "number", "required": True, "min": 1},
        ],
    },
    {
        "id": 3,
        "name": "Retail / Counter Scale",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "accuracyClass",
                "label": "Accuracy Class",
                "type": "select",
                "required": True,
                "options": _opts("II", "III"),
            },
            {
                "key": "maxCapacity",
                "label": "Max Capacity",
                "type": "unit-number",
                "unit": "kg",
                "required": True,
            },
            {
                "key": "minCapacity",
                "label": "Min Capacity",
                "type": "unit-number",
                "unit": "kg",
                "required": True,
            },
            {
                "key": "platformType",
                "label": "Platform type",
                "type": "select",
                "required": True,
                "options": _opts("single-pan", "dual-pan"),
            },
        ],
    },
    {
        "id": 4,
        "name": "Platform / Bench Scale",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "capacity",
                "label": "Capacity",
                "type": "select",
                "required": True,
                "presets": _opts("30 kg", "60 kg", "100 kg", "300 kg", "500 kg", "1000 kg"),
            },
            {
                "key": "accuracyClass",
                "label": "Accuracy Class",
                "type": "select",
                "required": True,
                "options": _opts("II", "III"),
            },
            {
                "key": "indicatorType",
                "label": "Indicator type",
                "type": "select",
                "required": True,
                "options": _opts("mechanical", "digital"),
            },
        ],
    },
    {
        "id": 5,
        "name": "Spring Balance",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "maxCapacity",
                "label": "Max Capacity",
                "type": "unit-number",
                "unit": "kg",
                "required": True,
            },
            {
                "key": "graduationInterval",
                "label": "Graduation interval",
                "type": "unit-number",
                "unit": "g",
                "required": True,
            },
            {
                "key": "dialType",
                "label": "Dial type",
                "type": "select",
                "required": True,
                "options": _opts("analog", "digital"),
            },
        ],
    },
    {
        "id": 6,
        "name": "Bullion / Precision Jewellery Scale",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "capacity",
                "label": "Capacity",
                "type": "select",
                "required": True,
                "presets": _opts("500 g", "1 kg", "2 kg", "5 kg"),
            },
            {
                "key": "readability",
                "label": "Readability",
                "type": "select",
                "required": True,
                "options": _opts("0.001 g", "0.01 g", "0.1 g"),
            },
            {
                "key": "accuracyClass",
                "label": "Class",
                "type": "select",
                "required": True,
                "options": _opts("I", "II"),
            },
        ],
    },
    {
        "id": 7,
        "name": "Measuring Tape (Length)",
        "validity_months": 24,
        "field_schema": [
            {
                "key": "nominalLength",
                "label": "Nominal Length",
                "type": "unit-number",
                "unit": "m",
                "required": True,
            },
            {
                "key": "material",
                "label": "Material",
                "type": "select",
                "required": True,
                "options": _opts("steel", "fibreglass", "cloth"),
            },
            {
                "key": "lengthClass",
                "label": "Class",
                "type": "select",
                "required": True,
                "options": _opts("I", "II", "III"),
            },
        ],
    },
    {
        "id": 8,
        "name": "Volumetric Capacity Measure",
        "validity_months": 24,
        "field_schema": [
            {
                "key": "nominalCapacity",
                "label": "Nominal Capacity",
                "type": "unit-number",
                "unit_options": ["L", "mL"],
                "required": True,
            },
            {
                "key": "material",
                "label": "Material",
                "type": "select",
                "required": True,
                "options": _opts("metal", "glass", "plastic"),
            },
            {
                "key": "measureType",
                "label": "Type",
                "type": "select",
                "required": True,
                "options": _opts("dry measure", "liquid measure"),
            },
        ],
    },
    {
        "id": 9,
        "name": "Metre Rod / Yardstick",
        "validity_months": 24,
        "field_schema": [
            {
                "key": "nominalLength",
                "label": "Nominal Length",
                "type": "unit-number",
                "unit": "m",
                "required": True,
            },
            {
                "key": "material",
                "label": "Material",
                "type": "select",
                "required": True,
                "options": _opts("wood", "steel", "aluminium"),
            },
        ],
    },
    {
        "id": 10,
        "name": "Road Weighbridge (Non-Automatic)",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "capacity",
                "label": "Capacity",
                "type": "select",
                "required": True,
                "presets": _opts("10 T", "20 T", "40 T", "60 T", "100 T"),
            },
            {
                "key": "platformLength",
                "label": "Platform Length",
                "type": "unit-number",
                "unit": "m",
                "required": True,
            },
            {
                "key": "loadCellCount",
                "label": "Number of load cells",
                "type": "number",
                "required": True,
                "min": 1,
            },
            {
                "key": "approachType",
                "label": "Approach type",
                "type": "select",
                "required": True,
                "options": _opts("pit", "pitless"),
            },
        ],
    },
    {
        "id": 11,
        "name": "Rail Weighbridge (Automatic)",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "capacity",
                "label": "Capacity",
                "type": "unit-number",
                "unit": "T",
                "required": True,
            },
            {
                "key": "operatingMode",
                "label": "Operating mode",
                "type": "toggle",
                "required": True,
                "options": _opts("Static", "Dynamic"),
            },
            {
                "key": "trackGauge",
                "label": "Track gauge",
                "type": "select",
                "required": True,
                "options": _opts("broad gauge", "metre gauge"),
            },
            {
                "key": "maxSpeed",
                "label": "Max speed (if Dynamic)",
                "type": "unit-number",
                "unit": "km/h",
                "help_text": "Shown only when Operating mode = Dynamic",
            },
        ],
    },
    {
        "id": 12,
        "name": "Electricity (Energy) Meter",
        "validity_months": 60,
        "field_schema": [
            {
                "key": "meterType",
                "label": "Meter type",
                "type": "select",
                "required": True,
                "options": _opts("electromechanical", "static/digital"),
            },
            {
                "key": "phase",
                "label": "Phase",
                "type": "select",
                "required": True,
                "options": _opts("single", "three"),
            },
            {
                "key": "ratedCurrent",
                "label": "Rated current",
                "type": "unit-number",
                "unit": "A",
                "required": True,
            },
            {
                "key": "ratedVoltage",
                "label": "Rated voltage",
                "type": "unit-number",
                "unit": "V",
                "required": True,
            },
        ],
    },
    {
        "id": 13,
        "name": "Domestic Gas Meter (Diaphragm)",
        "validity_months": 60,
        "field_schema": [
            {
                "key": "ratedCapacity",
                "label": "Rated capacity",
                "type": "unit-number",
                "unit": "m³/h",
                "required": True,
            },
            {
                "key": "connectionSize",
                "label": "Connection size",
                "type": "select",
                "required": True,
                "options": _opts('1"', '1.5"', '2"'),
            },
            {"key": "meterClass", "label": "Meter class", "type": "text", "required": True},
        ],
    },
    {
        "id": 14,
        "name": "Belt Conveyor Weigher (Automatic)",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "beltSpeed",
                "label": "Belt speed",
                "type": "unit-number",
                "unit": "m/s",
                "required": True,
            },
            {
                "key": "beltWidth",
                "label": "Belt width",
                "type": "unit-number",
                "unit": "mm",
                "required": True,
            },
            {
                "key": "operatingMode",
                "label": "Operating mode",
                "type": "toggle",
                "required": True,
                "options": _opts("Static", "Dynamic"),
                "help_text": "Static calibration run vs. live operation test",
            },
            {
                "key": "ratedCapacity",
                "label": "Rated capacity",
                "type": "unit-number",
                "unit": "T/h",
                "required": True,
            },
        ],
    },
    {
        "id": 15,
        "name": "Taximeter",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "vehicleRegNo",
                "label": "Vehicle registration number",
                "type": "text",
                "required": True,
            },
            {
                "key": "tariffRef",
                "label": "Tariff structure reference",
                "type": "text",
                "required": True,
            },
            {
                "key": "calibrationFactor",
                "label": "Wheel/tyre calibration factor",
                "type": "text",
            },
        ],
    },
    {
        "id": 16,
        "name": "Auto-rickshaw Fare Meter",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "vehicleRegNo",
                "label": "Vehicle registration number",
                "type": "text",
                "required": True,
            },
            {
                "key": "tariffCardRef",
                "label": "Tariff card reference",
                "type": "text",
                "required": True,
            },
        ],
    },
    {
        "id": 17,
        "name": "Water Meter",
        "validity_months": 60,
        "field_schema": [
            {
                "key": "nominalDiameter",
                "label": "Nominal diameter",
                "type": "select",
                "required": True,
                "options": _opts("15 mm", "20 mm", "25 mm", "40 mm", "50 mm"),
            },
            {
                "key": "flowRateBand",
                "label": "Flow rate band",
                "type": "range-band",
                "required": True,
                "unit": "m³/h",
                "help_text": "Qmin → Qt → Qmax; Qmin < Qt < Qmax",
            },
            {
                "key": "meterClass",
                "label": "Meter class",
                "type": "select",
                "required": True,
                "options": _opts("A", "B", "C", "D"),
            },
        ],
    },
    {
        "id": 18,
        "name": "Petrol / Diesel Dispensing Unit",
        "validity_months": 6,
        "field_schema": [
            {"key": "pumpBrand", "label": "Pump brand", "type": "text", "required": True},
            {
                "key": "mechanism",
                "label": "Electronic/mechanical",
                "type": "select",
                "required": True,
                "options": _opts("Electronic", "Mechanical"),
            },
            {
                "key": "nozzles",
                "label": "Nozzles",
                "type": "repeater",
                "required": True,
                "repeater_label": "+ Add Nozzle",
                "repeater_fields": [
                    {
                        "key": "fuelType",
                        "label": "Fuel type",
                        "type": "select",
                        "required": True,
                        "options": _opts("Petrol", "Diesel"),
                    },
                    {
                        "key": "flowRate",
                        "label": "Flow rate",
                        "type": "unit-number",
                        "unit": "L/min",
                        "required": True,
                    },
                    {
                        "key": "hoseLength",
                        "label": "Hose length",
                        "type": "unit-number",
                        "unit": "m",
                    },
                ],
            },
        ],
    },
    {
        "id": 19,
        "name": "Sphygmomanometer (BP Monitor)",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "instrumentType",
                "label": "Type",
                "type": "select",
                "required": True,
                "options": _opts("mercury", "aneroid", "digital"),
            },
            {
                "key": "cuffSize",
                "label": "Cuff size",
                "type": "select",
                "required": True,
                "options": _opts("adult", "paediatric", "large adult"),
            },
            {
                "key": "pressureRange",
                "label": "Pressure range",
                "type": "unit-number",
                "unit": "mmHg",
                "required": True,
            },
        ],
    },
    {
        "id": 20,
        "name": "Clinical Thermometer",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "instrumentType",
                "label": "Type",
                "type": "select",
                "required": True,
                "options": _opts("mercury-in-glass", "digital"),
            },
            {
                "key": "rangeMin",
                "label": "Range min",
                "type": "unit-number",
                "unit": "°C",
                "required": True,
            },
            {
                "key": "rangeMax",
                "label": "Range max",
                "type": "unit-number",
                "unit": "°C",
                "required": True,
            },
            {
                "key": "resolution",
                "label": "Resolution",
                "type": "select",
                "required": True,
                "options": _opts("0.1 °C", "0.5 °C"),
            },
        ],
    },
    {
        "id": 21,
        "name": "Tyre Pressure Gauge",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "gaugeType",
                "label": "Type",
                "type": "select",
                "required": True,
                "options": _opts("analog dial", "digital"),
            },
            {
                "key": "range",
                "label": "Range",
                "type": "unit-number",
                "unit_options": ["PSI", "kPa"],
                "required": True,
            },
            {
                "key": "application",
                "label": "Application",
                "type": "select",
                "required": True,
                "options": _opts("automotive", "heavy vehicle"),
            },
        ],
    },
    {
        "id": 22,
        "name": "Milk Analyzer / Milko-tester",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "parametersMeasured",
                "label": "Parameters measured",
                "type": "multiselect",
                "required": True,
                "options": _opts("Fat %", "SNF %", "Density", "Added Water"),
            },
            {
                "key": "throughput",
                "label": "Sample throughput",
                "type": "unit-number",
                "unit": "samples/hr",
            },
        ],
    },
    {
        "id": 23,
        "name": "Grain Moisture Meter",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "grainTypes",
                "label": "Grain types calibrated",
                "type": "multiselect",
                "required": True,
                "options": _opts("Wheat", "Rice", "Maize", "Pulses"),
            },
            {
                "key": "moistureRangeMin",
                "label": "Moisture range min",
                "type": "unit-number",
                "unit": "%",
                "required": True,
            },
            {
                "key": "moistureRangeMax",
                "label": "Moisture range max",
                "type": "unit-number",
                "unit": "%",
                "required": True,
            },
        ],
    },
    {
        "id": 24,
        "name": "Hydrometer / Densimeter",
        "validity_months": 24,
        "field_schema": [
            {
                "key": "scaleType",
                "label": "Scale type",
                "type": "select",
                "required": True,
                "options": _opts("specific gravity", "Baumé", "Brix", "alcohol"),
            },
            {"key": "rangeMin", "label": "Range min", "type": "number", "required": True},
            {"key": "rangeMax", "label": "Range max", "type": "number", "required": True},
        ],
    },
    {
        "id": 25,
        "name": "LPG / CNG Dispensing Unit",
        "validity_months": 6,
        "field_schema": [
            {
                "key": "gasType",
                "label": "Gas type",
                "type": "select",
                "required": True,
                "options": _opts("LPG", "CNG"),
            },
            {
                "key": "dispenserBrand",
                "label": "Dispenser brand",
                "type": "text",
                "required": True,
            },
            {
                "key": "nozzles",
                "label": "Nozzles",
                "type": "repeater",
                "required": True,
                "repeater_label": "+ Add Nozzle",
                "repeater_fields": [
                    {
                        "key": "position",
                        "label": "Nozzle position",
                        "type": "text",
                        "required": True,
                    },
                    {
                        "key": "flowRate",
                        "label": "Flow rate",
                        "type": "unit-number",
                        "unit_options": ["kg/min", "kg/s"],
                        "required": True,
                    },
                ],
            },
        ],
    },
    {
        "id": 26,
        "name": "Industrial Gas Meter (Turbine/Rotary)",
        "validity_months": 60,
        "field_schema": [
            {
                "key": "ratedCapacity",
                "label": "Rated capacity",
                "type": "unit-number",
                "unit": "m³/h",
                "required": True,
            },
            {
                "key": "flowRateBand",
                "label": "Flow rate band",
                "type": "range-band",
                "required": True,
                "unit": "m³/h",
                "help_text": "Qmin → Qt → Qmax; Qmin < Qt < Qmax",
            },
            {
                "key": "connectionSize",
                "label": "Connection size",
                "type": "select",
                "required": True,
                "options": _opts('2"', '3"', '4"', '6"'),
            },
        ],
    },
    {
        "id": 27,
        "name": "Automatic Checkweigher (Packaged Goods Line)",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "lineSpeed",
                "label": "Line speed",
                "type": "unit-number",
                "unit": "items/min",
                "required": True,
            },
            {
                "key": "weightRangeMin",
                "label": "Weight range min",
                "type": "unit-number",
                "unit_options": ["g", "kg"],
                "required": True,
            },
            {
                "key": "weightRangeMax",
                "label": "Weight range max",
                "type": "unit-number",
                "unit_options": ["g", "kg"],
                "required": True,
            },
            {
                "key": "rejectionMechanism",
                "label": "Rejection mechanism",
                "type": "select",
                "required": True,
                "options": _opts("pusher", "air-blast", "diverter"),
            },
        ],
    },
    {
        "id": 28,
        "name": "Hopper / Tank Weighing System",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "tankCapacity",
                "label": "Tank capacity",
                "type": "unit-number",
                "unit_options": ["T", "kL"],
                "required": True,
            },
            {
                "key": "loadCellCount",
                "label": "Number of load cells",
                "type": "number",
                "required": True,
                "min": 1,
            },
            {
                "key": "mountingType",
                "label": "Mounting type",
                "type": "select",
                "required": True,
                "options": _opts("suspended", "floor-mounted"),
            },
        ],
    },
    {
        "id": 29,
        "name": "Portable Axle-Load Weighbridge",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "capacityPerAxle",
                "label": "Capacity per axle",
                "type": "unit-number",
                "unit": "T",
                "required": True,
            },
            {
                "key": "padCount",
                "label": "Number of pads",
                "type": "select",
                "required": True,
                "options": _opts("2", "4", "6"),
            },
            {
                "key": "mounting",
                "label": "Portable/fixed",
                "type": "select",
                "required": True,
                "options": _opts("portable", "fixed"),
            },
        ],
    },
    {
        "id": 30,
        "name": "Bulk Liquid Flow Meter (Oil/Milk)",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "fluidType",
                "label": "Fluid type",
                "type": "select",
                "required": True,
                "options": _opts("edible oil", "fuel oil", "milk", "other"),
            },
            {
                "key": "ratedFlow",
                "label": "Rated flow",
                "type": "unit-number",
                "unit": "L/min",
                "required": True,
            },
            {
                "key": "meterType",
                "label": "Meter type",
                "type": "select",
                "required": True,
                "options": _opts("positive displacement", "turbine", "Coriolis"),
            },
        ],
    },
    {
        "id": 31,
        "name": "Speed Measuring Device (Radar/Laser Gun)",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "technology",
                "label": "Technology",
                "type": "select",
                "required": True,
                "options": _opts("radar", "LIDAR"),
            },
            {
                "key": "speedRangeMin",
                "label": "Speed range min",
                "type": "unit-number",
                "unit": "km/h",
                "required": True,
            },
            {
                "key": "speedRangeMax",
                "label": "Speed range max",
                "type": "unit-number",
                "unit": "km/h",
                "required": True,
            },
            {
                "key": "rangeRating",
                "label": "Range/distance rating",
                "type": "unit-number",
                "unit": "m",
            },
        ],
    },
    {
        "id": 32,
        "name": "Road Tanker / Bowser (Multi-Compartment)",
        "validity_months": 12,
        "field_schema": [
            {
                "key": "vehicleRegNo",
                "label": "Vehicle registration number",
                "type": "text",
                "required": True,
            },
            {
                "key": "compartments",
                "label": "Compartments",
                "type": "repeater",
                "required": True,
                "repeater_label": "+ Add Compartment",
                "repeater_fields": [
                    {
                        "key": "compartmentNumber",
                        "label": "Compartment number",
                        "type": "number",
                        "required": True,
                        "min": 1,
                    },
                    {
                        "key": "nominalCapacity",
                        "label": "Nominal capacity",
                        "type": "unit-number",
                        "unit": "L",
                        "required": True,
                    },
                    {
                        "key": "calibrationChart",
                        "label": "Calibration chart reference",
                        "type": "file",
                    },
                ],
            },
        ],
    },
    {
        "id": 33,
        "name": "Ring & Plug Gauge Set (Length Standards, Calibration Lab)",
        "validity_months": 36,
        "field_schema": [
            {
                "key": "gaugeType",
                "label": "Gauge type",
                "type": "select",
                "required": True,
                "options": _opts("ring", "plug", "both"),
            },
            {
                "key": "nominalDiameters",
                "label": "Nominal diameters",
                "type": "repeater",
                "required": True,
                "repeater_fields": [
                    {
                        "key": "diameter",
                        "label": "Diameter",
                        "type": "unit-number",
                        "unit": "mm",
                        "required": True,
                    },
                    {
                        "key": "toleranceGrade",
                        "label": "Tolerance grade",
                        "type": "select",
                        "required": True,
                        "options": _opts("IT01", "IT0", "IT1", "IT2"),
                    },
                ],
            },
        ],
    },
]

assert len(SEED_CATEGORIES) == 33
assert [c["id"] for c in SEED_CATEGORIES] == list(range(1, 34))


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "instrument_categories",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("validity_months", sa.Integer(), nullable=False),
        sa.Column("field_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instrument_categories")),
    )
    # ### end Alembic commands ###

    # Data-seed step: reference/taxonomy data, not demo data — see this file's own module
    # docstring and docs/specs/16-instrument-categories.md §9 D2 for why this lives in the
    # migration itself rather than app/seed.py/database/seed/.
    op.bulk_insert(
        sa.table(
            "instrument_categories",
            sa.column("id", sa.SmallInteger()),
            sa.column("name", sa.Text()),
            sa.column("validity_months", sa.Integer()),
            sa.column("field_schema", postgresql.JSONB()),
        ),
        [
            {
                "id": c["id"],
                "name": c["name"],
                "validity_months": c["validity_months"],
                "field_schema": c["field_schema"],
            }
            for c in SEED_CATEGORIES
        ],
    )

    # instruments.category_id / instruments.category_values: additive, nullable, no backfill —
    # every existing instrument keeps category_id = NULL and continues to work entirely off
    # instrument_type/capacity/capacity_unit/accuracy_class (spec 16 "out of scope": no attempt to
    # map old rows onto the new 33 categories).
    op.add_column(
        "instruments",
        sa.Column("category_id", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "instruments",
        sa.Column("category_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_instruments_category_id_instrument_categories"),
        "instruments",
        "instrument_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_instruments_category_id_instrument_categories"),
        "instruments",
        type_="foreignkey",
    )
    op.drop_column("instruments", "category_values")
    op.drop_column("instruments", "category_id")

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("instrument_categories")
    # ### end Alembic commands ###
