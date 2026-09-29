"""Static region list (demo subset).

ASSUMPTION: project conventions, not official state/district codes. Replace with the full
official list before production.
"""

from typing import TypedDict


class State(TypedDict):
    name: str
    districts: dict[str, str]


REGIONS: dict[str, State] = {
    "JH": {"name": "Jharkhand", "districts": {"DHN": "Dhanbad", "RNC": "Ranchi", "BKR": "Bokaro"}},
    "BR": {"name": "Bihar", "districts": {"PAT": "Patna"}},
}


def is_valid_state(state_code: str | None) -> bool:
    return state_code in REGIONS


def is_valid_region(state_code: str | None, district_code: str | None) -> bool:
    state = REGIONS.get(state_code or "")
    return state is not None and district_code in state["districts"]
