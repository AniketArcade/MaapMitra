"""Which instrument fields an active application locks (spec 03 §9, spec 05 §7).

Lives in `core/`, not `services/instruments.py`, because both `services/instruments.py` and
`schemas/instrument.py` need it and `services/instruments.py` already imports from
`schemas/instrument.py` — putting it in the service module would create a cycle.
"""

from app.core.application_types import TERMINAL_STATUSES, ApplicationStatus

IDENTITY_LOCKED = frozenset(
    {
        "manufacturer",
        "model",
        "serial_number",
        "capacity",
        "capacity_unit",
        "accuracy_class",
        "state_code",
        "district_code",
        # Spec 14: joins state_code/district_code for the same reason — it's snapshotted onto
        # the Application at creation (verification_mode), so letting it change mid-application
        # would desync the instrument's live value from the application's frozen snapshot and
        # let a business "regame" the office/on-site routing decision after the fact, even though
        # the current application's own verification_mode wouldn't retroactively change either way.
        "transportable",
        # Spec 16: category_id/category_values join IDENTITY_LOCKED for the same reason as
        # transportable just above — an application snapshot's own understanding of "what kind of
        # instrument is this" shouldn't have its underlying instrument's category (or the filled-in
        # values that describe it) silently change out from under it while a non-terminal
        # application is in progress. Locked/unlocked as a pair, same as the create/update schema
        # pairing rule (schemas/instrument.py) — never one without the other.
        "category_id",
        "category_values",
    }
)
# address / latitude / longitude lock only once an inspection is scheduled: a business can
# still fix a typo while review is in progress.
LOCATION_FIELDS = frozenset({"address", "latitude", "longitude"})
LOCATION_LOCK_STATUSES = frozenset(
    {ApplicationStatus.SCHEDULED, ApplicationStatus.INSPECTION, ApplicationStatus.APPROVED}
)

LOCATION_LOCK_MESSAGE = (
    "An inspection is scheduled for this instrument; its address and coordinates can't be "
    "changed until the application is completed or rejected."
)


def locked_fields(active_status: ApplicationStatus | None) -> frozenset[str]:
    """Fields InstrumentUpdate must refuse, given the instrument's active application's status
    (None if it has none). Single source of truth for both the PATCH check and InstrumentOut,
    so the frontend disables exactly what the backend enforces (spec 05 D10).

    Defensively treats a terminal status the same as None: callers normally only ever pass a
    non-terminal status (Instrument.active_application's primaryjoin already excludes
    TERMINAL_STATUSES), but nothing locks if the caller passed one directly anyway.
    """
    if active_status is None or active_status in TERMINAL_STATUSES:
        return frozenset()
    locked = IDENTITY_LOCKED
    if active_status in LOCATION_LOCK_STATUSES:
        locked = locked | LOCATION_FIELDS
    return locked
