"""Static region list.

Covers all 28 states + 8 union territories, using the standard 2-letter vehicle-registration
state codes (stable, not subject to the frequent district-boundary reorganizations India's states
have gone through in recent years). Jharkhand and Bihar carry a few illustrative districts each
(leftover demo detail, Dhanbad being this project's demo city); every other state/UT carries
exactly one representative district (its capital or largest city) so the full state list renders
and is navigable end to end.

ASSUMPTION: district *names and codes* here are a best-effort, non-exhaustive list from the
author's own knowledge, not pulled from an official registry (e.g. the Census/LGD code list), and
every state besides Jharkhand/Bihar is deliberately reduced to one district. Verify against an
authoritative source and fill in each state's remaining districts before production use.
"""

from typing import TypedDict


class State(TypedDict):
    name: str
    districts: dict[str, str]


REGIONS: dict[str, State] = {
    "JH": {"name": "Jharkhand", "districts": {"DHN": "Dhanbad", "RNC": "Ranchi", "BKR": "Bokaro"}},
    "BR": {"name": "Bihar", "districts": {"PAT": "Patna"}},
    "AP": {"name": "Andhra Pradesh", "districts": {"GNT": "Guntur"}},
    "AR": {"name": "Arunachal Pradesh", "districts": {"ITN": "Itanagar"}},
    "AS": {"name": "Assam", "districts": {"GHY": "Guwahati"}},
    "CG": {"name": "Chhattisgarh", "districts": {"RPR": "Raipur"}},
    "GA": {"name": "Goa", "districts": {"PNJ": "Panaji"}},
    "GJ": {"name": "Gujarat", "districts": {"GNDN": "Gandhinagar"}},
    "HR": {"name": "Haryana", "districts": {"GGN": "Gurugram"}},
    "HP": {"name": "Himachal Pradesh", "districts": {"SML": "Shimla"}},
    "KA": {"name": "Karnataka", "districts": {"BLR": "Bengaluru"}},
    "KL": {"name": "Kerala", "districts": {"TVM": "Thiruvananthapuram"}},
    "MP": {"name": "Madhya Pradesh", "districts": {"BPL": "Bhopal"}},
    "MH": {"name": "Maharashtra", "districts": {"MUM": "Mumbai"}},
    "MN": {"name": "Manipur", "districts": {"IMP": "Imphal"}},
    "ML": {"name": "Meghalaya", "districts": {"SHL": "Shillong"}},
    "MZ": {"name": "Mizoram", "districts": {"AIZ": "Aizawl"}},
    "NL": {"name": "Nagaland", "districts": {"KOH": "Kohima"}},
    "OD": {"name": "Odisha", "districts": {"BBSR": "Bhubaneswar"}},
    "PB": {"name": "Punjab", "districts": {"ASR": "Amritsar"}},
    "RJ": {"name": "Rajasthan", "districts": {"JAI": "Jaipur"}},
    "SK": {"name": "Sikkim", "districts": {"GTK": "Gangtok"}},
    "TN": {"name": "Tamil Nadu", "districts": {"CHN": "Chennai"}},
    "TS": {"name": "Telangana", "districts": {"HYD": "Hyderabad"}},
    "TR": {"name": "Tripura", "districts": {"AGT": "Agartala"}},
    "UP": {"name": "Uttar Pradesh", "districts": {"LKO": "Lucknow"}},
    "UK": {"name": "Uttarakhand", "districts": {"DDN": "Dehradun"}},
    "WB": {"name": "West Bengal", "districts": {"KOL": "Kolkata"}},
    "AN": {"name": "Andaman and Nicobar Islands", "districts": {"PBR": "Port Blair"}},
    "CH": {"name": "Chandigarh", "districts": {"CHD": "Chandigarh"}},
    "DN": {"name": "Dadra and Nagar Haveli and Daman and Diu", "districts": {"DMN": "Daman"}},
    "DL": {"name": "Delhi", "districts": {"NDL": "New Delhi"}},
    "JK": {"name": "Jammu and Kashmir", "districts": {"SRI": "Srinagar"}},
    "LA": {"name": "Ladakh", "districts": {"LEH": "Leh"}},
    "LD": {"name": "Lakshadweep", "districts": {"KVR": "Kavaratti"}},
    "PY": {"name": "Puducherry", "districts": {"PDY": "Puducherry"}},
}


def is_valid_state(state_code: str | None) -> bool:
    return state_code in REGIONS


def is_valid_region(state_code: str | None, district_code: str | None) -> bool:
    state = REGIONS.get(state_code or "")
    return state is not None and district_code in state["districts"]
