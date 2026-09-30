"""Per-instrument-type field-inspection checklist and measurement templates (step 6).

ASSUMPTION: illustrative demo content, not sourced from an actual Legal Metrology inspection
manual or an OIML recommendation. Verify with a domain expert before any non-demo use — the
same caveat core/instrument_types.py and core/application_types.py already carry for their own
categories.

Measurement points are fractions of the instrument's own `capacity`, resolved to an actual
expected_value/unit only when an inspection starts (services/applications.py's transition()):
multi-point load testing at fractions of rated capacity approximates real verification
procedure (e.g. OIML R76 for weighing instruments), but exact legal tolerance formulas are not
encoded anywhere. The officer judges pass/fail by eye, recorded per checklist item as `result`,
using the instrument's own `accuracy_class` — `observed_value` is recorded for the record, not
used to auto-compute a verdict.
"""

from collections import Counter
from collections.abc import Iterable
from typing import NamedTuple

from app.core.instrument_types import InstrumentType


class ChecklistItemDef(NamedTuple):
    key: str
    label: str


CHECKLIST_TEMPLATES: dict[InstrumentType, list[ChecklistItemDef]] = {
    InstrumentType.WEIGHING_SCALE: [
        ChecklistItemDef("seal_intact", "Verification/seal mark intact"),
        ChecklistItemDef("no_damage", "No visible damage or corrosion"),
        ChecklistItemDef("platform_level", "Platform/pan level and stable"),
        ChecklistItemDef("zero_setting", "Zero-setting functions correctly"),
        ChecklistItemDef("display_legible", "Display legible and accurate"),
        ChecklistItemDef("tare_function", "Tare function works correctly"),
        ChecklistItemDef("repeatability", "Repeat readings are consistent (repeatability check)"),
    ],
    InstrumentType.WEIGHBRIDGE: [
        ChecklistItemDef("seal_intact", "Verification/seal mark intact"),
        ChecklistItemDef("no_damage", "No visible damage to platform or approach ramps"),
        ChecklistItemDef("platform_level", "Weighbridge platform level and stable"),
        ChecklistItemDef("zero_setting", "Zero-setting functions correctly"),
        ChecklistItemDef("display_legible", "Display/printout legible and accurate"),
        ChecklistItemDef("load_cell_condition", "Load cells and foundation in good condition"),
        ChecklistItemDef("repeatability", "Repeat readings are consistent (repeatability check)"),
    ],
    InstrumentType.WEIGHT: [
        ChecklistItemDef("seal_intact", "Verification/seal mark intact"),
        ChecklistItemDef("no_damage", "No visible damage, corrosion or wear"),
        ChecklistItemDef("marking_legible", "Nominal value marking legible"),
        ChecklistItemDef("surface_clean", "Surface clean, free of adhering material"),
        ChecklistItemDef("shape_intact", "Shape and adjustment cavity intact (not tampered)"),
    ],
    InstrumentType.FUEL_DISPENSER: [
        ChecklistItemDef("seal_intact", "Verification/seal mark intact"),
        ChecklistItemDef("no_damage", "No visible damage or leakage"),
        ChecklistItemDef("zero_setting", "Zero-setting/reset functions correctly"),
        ChecklistItemDef("display_legible", "Display legible and accurate"),
        ChecklistItemDef("hose_nozzle_condition", "Hose and nozzle in good condition, no leaks"),
        ChecklistItemDef("repeatability", "Repeat deliveries are consistent (repeatability check)"),
    ],
    InstrumentType.MEASURE_LENGTH: [
        ChecklistItemDef("seal_intact", "Verification/seal mark intact"),
        ChecklistItemDef("no_damage", "No visible damage, bending or wear"),
        ChecklistItemDef("marking_legible", "Graduation marks legible and evenly spaced"),
        ChecklistItemDef("straightness", "Measure is straight/flat, not warped"),
        ChecklistItemDef("end_condition", "End faces/hooks in good condition"),
    ],
    InstrumentType.MEASURE_VOLUME: [
        ChecklistItemDef("seal_intact", "Verification/seal mark intact"),
        ChecklistItemDef("no_damage", "No visible damage, dents or leaks"),
        ChecklistItemDef("marking_legible", "Capacity marking legible"),
        ChecklistItemDef("interior_clean", "Interior clean, free of residue or deposits"),
        ChecklistItemDef("level_stable", "Vessel stable and level when filled"),
    ],
    InstrumentType.OTHER: [
        ChecklistItemDef("seal_intact", "Verification/seal mark intact"),
        ChecklistItemDef("no_damage", "No visible damage or corrosion"),
        ChecklistItemDef("marking_legible", "Nameplate/marking legible"),
        ChecklistItemDef("functions_correctly", "Instrument functions correctly"),
    ],
}

# Fractions of the instrument's own `capacity`, resolved to an expected_value/unit at start time.
MEASUREMENT_TEMPLATES: dict[InstrumentType, list[float]] = {
    InstrumentType.WEIGHING_SCALE: [0.25, 0.5, 0.75, 1.0],
    InstrumentType.WEIGHBRIDGE: [0.25, 0.5, 0.75, 1.0],
    InstrumentType.FUEL_DISPENSER: [0.25, 0.5, 0.75, 1.0],
    InstrumentType.MEASURE_VOLUME: [0.25, 0.5, 0.75, 1.0],
    InstrumentType.MEASURE_LENGTH: [0.25, 0.5, 0.75, 1.0],
    InstrumentType.WEIGHT: [1.0],  # a reference standard, not a ranged device: one point
    InstrumentType.OTHER: [1.0],
}


def measurement_label(fraction: float) -> str:
    return f"{int(fraction * 100)}% of capacity"


def checklist_summary_counts(results: Iterable[str | None]) -> dict[str, int]:
    """Counts of PASS/FAIL/NA among the given checklist item results; None entries ignored."""
    counts = Counter(r for r in results if r is not None)
    return {r: counts.get(r, 0) for r in ("PASS", "FAIL", "NA")}
