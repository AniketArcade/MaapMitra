"""Spec 16: the 33 instrument categories (`instrument_categories` table), `GET
/instruments/meta`'s `categories` entry, `category_id`/`category_values` on
`InstrumentCreate`/`Update`/`Out`, the required-field-only validation scope, and
`category_id`/`category_values` joining `IDENTITY_LOCKED`.

ASSUMPTION (carried from docs/specs/16-instrument-categories.md): the seeded category content is
ported from a separate prototype repo's own invented-but-plausible fixture data, not sourced from
the real Legal Metrology Act 2009 — these tests only check structural/behavioral correctness, not
the legal accuracy of any category's fields.
"""

from fastapi.testclient import TestClient

from app.core.application_types import ApplicationStatus as _S
from app.core.instrument_lock import IDENTITY_LOCKED, locked_fields
from app.core.roles import Role
from tests.conftest import auth_header, instrument_body


def _create_instrument(client: TestClient, owner, **overrides):  # noqa: ANN001, ANN201
    return client.post(
        "/api/instruments", json=instrument_body(**overrides), headers=auth_header(owner)
    )


def _patch_instrument(client: TestClient, owner, instrument_id, body: dict):  # noqa: ANN001, ANN201
    return client.patch(f"/api/instruments/{instrument_id}", json=body, headers=auth_header(owner))


def _create_application(client: TestClient, owner, instrument_id):  # noqa: ANN001, ANN201
    return client.post(
        "/api/applications",
        json={"instrument_id": str(instrument_id), "application_type": "VERIFICATION"},
        headers=auth_header(owner),
    )


# ---------------------------------------------------------------------------
# (a) GET /instruments/meta serves all 33 categories, with correct field_schema
#     shape for a handful of representative/special-case ones.
# ---------------------------------------------------------------------------


def _meta(client: TestClient, user) -> dict:  # noqa: ANN001
    return client.get("/api/instruments/meta", headers=auth_header(user)).json()


def test_meta_includes_all_33_categories(client: TestClient, make_user) -> None:  # noqa: ANN001
    body = _meta(client, make_user(Role.BUSINESS))
    categories = body["categories"]
    assert len(categories) == 33
    assert [c["id"] for c in categories] == list(range(1, 34))
    # Every category has a name, a positive validity, and a non-empty field_schema.
    for c in categories:
        assert c["name"]
        assert c["validity_months"] > 0
        assert len(c["field_schema"]) > 0


def _category(categories: list[dict], category_id: int) -> dict:
    return next(c for c in categories if c["id"] == category_id)


def _field(category: dict, key: str) -> dict:
    return next(f for f in category["field_schema"] if f["key"] == key)


def test_meta_category_1_weight_repeater_shape(client: TestClient, make_user) -> None:  # noqa: ANN001
    categories = _meta(client, make_user(Role.BUSINESS))["categories"]
    category = _category(categories, 1)
    assert category["name"] == "Standard Weights"
    assert category["validity_months"] == 24

    denominations = _field(category, "denominations")
    assert denominations["type"] == "repeater"
    assert denominations["required"] is True
    assert denominations["repeater_label"] == "+ Add Weight"
    assert len(denominations["repeater_fields"]) == 1
    nominal_value = denominations["repeater_fields"][0]
    assert nominal_value["key"] == "nominalValue"
    assert nominal_value["type"] == "unit-number"
    assert nominal_value["unit_options"] == ["kg", "g"]
    assert nominal_value["required"] is True


def test_meta_category_2_locked_carat_unit(client: TestClient, make_user) -> None:  # noqa: ANN001
    categories = _meta(client, make_user(Role.BUSINESS))["categories"]
    category = _category(categories, 2)
    nominal_value = _field(category, "denominations")["repeater_fields"][0]
    # Locked unit "ct" (CLAUDE.md §8's "locked units" special case), not a unit_options toggle.
    assert nominal_value["unit"] == "ct"
    assert nominal_value.get("unit_options") is None


def test_meta_category_11_static_dynamic_toggle(client: TestClient, make_user) -> None:  # noqa: ANN001
    categories = _meta(client, make_user(Role.BUSINESS))["categories"]
    category = _category(categories, 11)
    assert category["name"] == "Rail Weighbridge (Automatic)"
    operating_mode = _field(category, "operatingMode")
    assert operating_mode["type"] == "toggle"
    assert operating_mode["required"] is True
    assert [o["value"] for o in operating_mode["options"]] == ["Static", "Dynamic"]


def test_meta_category_17_qmin_qt_qmax_range_band(client: TestClient, make_user) -> None:  # noqa: ANN001
    categories = _meta(client, make_user(Role.BUSINESS))["categories"]
    category = _category(categories, 17)
    assert category["name"] == "Water Meter"
    flow_rate_band = _field(category, "flowRateBand")
    assert flow_rate_band["type"] == "range-band"
    assert flow_rate_band["required"] is True
    assert flow_rate_band["unit"] == "m³/h"
    assert "Qmin" in flow_rate_band["help_text"]


def test_meta_category_18_add_nozzle_repeater(client: TestClient, make_user) -> None:  # noqa: ANN001
    categories = _meta(client, make_user(Role.BUSINESS))["categories"]
    category = _category(categories, 18)
    nozzles = _field(category, "nozzles")
    assert nozzles["type"] == "repeater"
    assert nozzles["repeater_label"] == "+ Add Nozzle"
    keys = [f["key"] for f in nozzles["repeater_fields"]]
    assert keys == ["fuelType", "flowRate", "hoseLength"]


def test_meta_category_32_add_compartment_repeater(client: TestClient, make_user) -> None:  # noqa: ANN001
    categories = _meta(client, make_user(Role.BUSINESS))["categories"]
    category = _category(categories, 32)
    compartments = _field(category, "compartments")
    assert compartments["type"] == "repeater"
    assert compartments["repeater_label"] == "+ Add Compartment"


def test_meta_category_20_locked_celsius_unit(client: TestClient, make_user) -> None:  # noqa: ANN001
    categories = _meta(client, make_user(Role.BUSINESS))["categories"]
    category = _category(categories, 20)
    assert category["name"] == "Clinical Thermometer"
    assert _field(category, "rangeMin")["unit"] == "°C"
    assert _field(category, "rangeMax")["unit"] == "°C"


# ---------------------------------------------------------------------------
# (b) creating an instrument with a valid category_id + category_values
#     satisfying all required fields succeeds.
# ---------------------------------------------------------------------------


def test_create_instrument_with_valid_category_values(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    # Category 15 (Taximeter): vehicleRegNo + tariffRef required, calibrationFactor optional.
    res = _create_instrument(
        client,
        owner,
        category_id=15,
        category_values={"vehicleRegNo": "JH01AB1234", "tariffRef": "Standard tariff card #4"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["category_id"] == 15
    assert body["category_values"] == {
        "vehicleRegNo": "JH01AB1234",
        "tariffRef": "Standard tariff card #4",
    }


# ---------------------------------------------------------------------------
# (c) category_id set but a required field missing from category_values -> 422
# ---------------------------------------------------------------------------


def test_create_instrument_missing_required_category_field_is_422(
    client: TestClient, make_user
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    # tariffRef is required for category 15 and is omitted here.
    res = _create_instrument(
        client, owner, category_id=15, category_values={"vehicleRegNo": "JH01AB1234"}
    )
    assert res.status_code == 422, res.text
    assert "tariffRef" in res.text


def test_create_instrument_unknown_category_id_is_422(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    res = _create_instrument(client, owner, category_id=999, category_values={"x": "y"})
    assert res.status_code == 422, res.text


# ---------------------------------------------------------------------------
# (d) category_id without category_values, or vice versa, is rejected
# ---------------------------------------------------------------------------


def test_create_instrument_category_id_without_values_is_422(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    res = _create_instrument(client, owner, category_id=15)
    assert res.status_code == 422, res.text


def test_create_instrument_category_values_without_id_is_422(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    res = _create_instrument(client, owner, category_values={"vehicleRegNo": "JH01AB1234"})
    assert res.status_code == 422, res.text


def test_patch_instrument_category_id_without_values_is_422(
    client: TestClient, make_user, make_instrument
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    res = _patch_instrument(client, owner, instrument.id, {"category_id": 15})
    assert res.status_code == 422, res.text


# ---------------------------------------------------------------------------
# (e) an instrument created the OLD way (no category_id, just instrument_type)
#     still works completely unaffected -- the key additivity regression test.
# ---------------------------------------------------------------------------


def test_create_instrument_without_category_is_unaffected(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    res = _create_instrument(client, owner)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["category_id"] is None
    assert body["category_values"] is None
    assert body["instrument_type"] == "WEIGHING_SCALE"


# ---------------------------------------------------------------------------
# (f) category_id/category_values lock the same way transportable does, once a
#     non-terminal application exists.
# ---------------------------------------------------------------------------


def test_category_fields_are_identity_locked() -> None:
    assert "category_id" in IDENTITY_LOCKED
    assert "category_values" in IDENTITY_LOCKED
    assert "category_id" in locked_fields(_S.SUBMITTED)
    assert "category_id" not in locked_fields(None)
    assert "category_id" not in locked_fields(_S.REJECTED)


def test_category_locked_while_application_in_progress(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    make_application(owner, instrument, status="SUBMITTED")

    res = _patch_instrument(
        client,
        owner,
        instrument.id,
        {"category_id": 15, "category_values": {"vehicleRegNo": "JH01AB1234", "tariffRef": "R1"}},
    )
    assert res.status_code == 409
    assert "application in progress" in res.json()["detail"]


def test_category_lock_lifts_after_rejection(
    client: TestClient, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    make_application(owner, instrument, status="REJECTED")

    res = _patch_instrument(
        client,
        owner,
        instrument.id,
        {"category_id": 15, "category_values": {"vehicleRegNo": "JH01AB1234", "tariffRef": "R1"}},
    )
    assert res.status_code == 200, res.text
    assert res.json()["category_id"] == 15


def test_application_creation_unaffected_by_category(
    client: TestClient, make_user, make_instrument
) -> None:  # noqa: ANN001
    """Categories are an instrument-only concept in this step; application creation and its
    verification_mode snapshot (spec 14) are entirely untouched, with or without a category."""
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    res = _create_application(client, owner, instrument.id)
    assert res.status_code == 201, res.text
