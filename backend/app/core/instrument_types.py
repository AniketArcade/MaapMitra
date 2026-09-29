"""Instrument categories.

ASSUMPTION: MVP product categories, NOT the legal classification under the Legal Metrology
Act 2009 or its rules. Verify with a domain expert before production.
"""

from enum import StrEnum


class InstrumentType(StrEnum):
    WEIGHING_SCALE = "WEIGHING_SCALE"
    WEIGHBRIDGE = "WEIGHBRIDGE"
    WEIGHT = "WEIGHT"
    FUEL_DISPENSER = "FUEL_DISPENSER"
    MEASURE_LENGTH = "MEASURE_LENGTH"
    MEASURE_VOLUME = "MEASURE_VOLUME"
    OTHER = "OTHER"


class CapacityUnit(StrEnum):
    mg = "mg"
    g = "g"
    kg = "kg"
    t = "t"
    mL = "mL"
    L = "L"
    kL = "kL"
    mm = "mm"
    cm = "cm"
    m = "m"


class AccuracyClass(StrEnum):
    """OIML weighing accuracy classes. Applicability per type is unverified (optional field)."""

    I = "I"  # noqa: E741
    II = "II"
    III = "III"
    IIII = "IIII"


TYPE_LABELS: dict[InstrumentType, str] = {
    InstrumentType.WEIGHING_SCALE: "Weighing scale",
    InstrumentType.WEIGHBRIDGE: "Weighbridge",
    InstrumentType.WEIGHT: "Weight",
    InstrumentType.FUEL_DISPENSER: "Fuel dispenser",
    InstrumentType.MEASURE_LENGTH: "Length measure",
    InstrumentType.MEASURE_VOLUME: "Volume measure",
    InstrumentType.OTHER: "Other",
}

_MASS = (CapacityUnit.mg, CapacityUnit.g, CapacityUnit.kg, CapacityUnit.t)
_VOLUME = (CapacityUnit.mL, CapacityUnit.L, CapacityUnit.kL)
_LENGTH = (CapacityUnit.mm, CapacityUnit.cm, CapacityUnit.m)

# Ordered tuples so the frontend dropdown order is stable.
UNIT_FAMILY: dict[InstrumentType, tuple[CapacityUnit, ...]] = {
    InstrumentType.WEIGHING_SCALE: _MASS,
    InstrumentType.WEIGHBRIDGE: _MASS,
    InstrumentType.WEIGHT: _MASS,
    InstrumentType.FUEL_DISPENSER: _VOLUME,
    InstrumentType.MEASURE_VOLUME: _VOLUME,
    InstrumentType.MEASURE_LENGTH: _LENGTH,
    InstrumentType.OTHER: tuple(CapacityUnit),
}
