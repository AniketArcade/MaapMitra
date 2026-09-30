"""Verification mode (spec `docs/specs/14-transportability.md`).

Whether an instrument's verification activity happens at an office/test centre or on-site
in-situ, derived from whether the instrument can be transported there.

Lives in its own module, not `instrument_types.py`: that file groups the instrument's own
physical/product categories (`InstrumentType`, `CapacityUnit`, `AccuracyClass`) — closely-related
enums for one domain area, per this repo's existing per-area grouping convention (mirrored by
`application_types.py` for the application/document lifecycle). Verification mode is a routing
concept computed from an instrument property (`Instrument.transportable`) but stored on the
Application (snapshotted at creation, see `app/services/applications.py: create()`), so it gets
its own small sibling module rather than crowding either existing one.
"""

from enum import StrEnum


class VerificationMode(StrEnum):
    OFFICE_TEST_CENTRE = "OFFICE_TEST_CENTRE"
    ON_SITE = "ON_SITE"


VERIFICATION_MODE_LABELS: dict[VerificationMode, str] = {
    VerificationMode.OFFICE_TEST_CENTRE: "Office / test centre",
    VerificationMode.ON_SITE: "On-site (in-situ)",
}


def verification_mode_for(transportable: bool) -> VerificationMode:
    """The snapshot mapping used once, at application creation (spec 14 §1): a transportable
    instrument is verified at an office/test centre; a non-transportable one is verified
    on-site/in-situ. Never re-derived after creation — `Application.verification_mode` freezes
    whatever this returned at the time, even if `Instrument.transportable` changes later."""
    return VerificationMode.OFFICE_TEST_CENTRE if transportable else VerificationMode.ON_SITE
