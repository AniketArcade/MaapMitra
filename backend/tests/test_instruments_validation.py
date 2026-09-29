import pytest
from fastapi.testclient import TestClient

from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Instrument
from tests.conftest import auth_header, instrument_body
from tests.helpers import audit_rows


@pytest.fixture
def owner(make_user):  # noqa: ANN001, ANN201
    return make_user(Role.BUSINESS)


def _post(client: TestClient, owner, **overrides):  # noqa: ANN001, ANN202
    return client.post(
        "/api/instruments", json=instrument_body(**overrides), headers=auth_header(owner)
    )


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"capacity_unit": "L"}, "capacity_unit"),  # volume unit on a scale
        ({"instrument_type": "MEASURE_LENGTH", "capacity_unit": "kg"}, "capacity_unit"),
        ({"capacity": 0}, "capacity"),
        ({"capacity": -5}, "capacity"),
        ({"capacity": "1.2345"}, "capacity"),
        ({"latitude": 23.79}, "longitude"),
        ({"longitude": 86.43}, "latitude"),
        ({"latitude": 91, "longitude": 86}, "latitude"),
        ({"latitude": 23, "longitude": 181}, "longitude"),
        ({"state_code": "XX"}, "state_code"),
        ({"state_code": "BR", "district_code": "DHN"}, "district_code"),
        ({"state_code": "BR"}, "district_code"),  # district defaults to org's DHN, not in BR
        ({"serial_number": "XYZ 123"}, "serial_number"),
        ({"serial_number": "XYZ#123"}, "serial_number"),
        ({"manufacturer": "   "}, "manufacturer"),
        ({"instrument_uid": "LM-JH-DHN-999999"}, "instrument_uid"),
        ({"created_by": "00000000-0000-0000-0000-000000000000"}, "created_by"),
    ],
)
def test_create_validation(client: TestClient, owner, overrides: dict, field: str) -> None:  # noqa: ANN001
    res = _post(client, owner, **overrides)
    assert res.status_code == 422, res.text
    assert field in {str(e["loc"][-1]) for e in res.json()["detail"]}


def test_other_type_accepts_any_unit(client: TestClient, owner) -> None:  # noqa: ANN001
    assert _post(client, owner, instrument_type="OTHER", capacity_unit="m").status_code == 201


def test_normalisation(client: TestClient, owner) -> None:  # noqa: ANN001
    res = _post(
        client,
        owner,
        serial_number="  xyz-12.3_4/5 ",
        manufacturer="  Essae   Teraoka ",
        latitude=23.7956781234,
        longitude=86.4303859999,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["serial_number"] == "XYZ-12.3_4/5"
    assert body["manufacturer"] == "Essae Teraoka"
    assert (body["latitude"], body["longitude"]) == (23.795678, 86.430386)
    assert body["capacity"] == 500.0 and isinstance(body["capacity"], float)


def test_location_defaults_to_org(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS, org_state="JH", org_district="BKR")
    body = _post(client, owner).json()
    assert (body["state_code"], body["district_code"]) == ("JH", "BKR")


@pytest.fixture
def instrument(make_instrument, owner):  # noqa: ANN001, ANN201
    return make_instrument(owner, latitude="23.79", longitude="86.43", accuracy_class="III")


def _patch(client: TestClient, owner, instrument, body: dict):  # noqa: ANN001, ANN202
    return client.patch(f"/api/instruments/{instrument.id}", json=body, headers=auth_header(owner))


def test_patch_single_coordinate_when_other_exists(client: TestClient, owner, instrument) -> None:  # noqa: ANN001
    res = _patch(client, owner, instrument, {"latitude": 23.8})
    assert res.status_code == 200 and res.json()["latitude"] == 23.8


def test_patch_single_coordinate_when_both_null(client: TestClient, owner, make_instrument) -> None:  # noqa: ANN001
    bare = make_instrument(owner)
    res = _patch(client, owner, bare, {"latitude": 23.8})
    assert res.status_code == 422


def test_patch_clear_both_coordinates(client: TestClient, owner, instrument) -> None:  # noqa: ANN001
    res = _patch(client, owner, instrument, {"latitude": None, "longitude": None})
    assert res.status_code == 200 and res.json()["latitude"] is None
    assert _patch(client, owner, instrument, {"latitude": 1.0}).status_code == 422


def test_patch_unit_outside_type_family(client: TestClient, owner, instrument) -> None:  # noqa: ANN001
    res = _patch(client, owner, instrument, {"capacity_unit": "mL"})
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "capacity_unit"]
    assert _patch(client, owner, instrument, {"capacity_unit": "t"}).status_code == 200


def test_patch_null_rules(client: TestClient, owner, instrument) -> None:  # noqa: ANN001
    assert _patch(client, owner, instrument, {"manufacturer": None}).status_code == 422
    assert _patch(client, owner, instrument, {"capacity": None}).status_code == 422
    res = _patch(client, owner, instrument, {"accuracy_class": None})
    assert res.status_code == 200 and res.json()["accuracy_class"] is None


def test_patch_type_or_unknown_field_rejected(client: TestClient, owner, instrument) -> None:  # noqa: ANN001
    assert _patch(client, owner, instrument, {"instrument_type": "WEIGHT"}).status_code == 422
    assert _patch(client, owner, instrument, {"instrument_uid": "LM-X"}).status_code == 422


def test_patch_region_merged(client: TestClient, owner, instrument) -> None:  # noqa: ANN001
    assert _patch(client, owner, instrument, {"state_code": "BR"}).status_code == 422
    res = _patch(client, owner, instrument, {"state_code": "BR", "district_code": "PAT"})
    assert res.status_code == 200


def test_empty_diff_is_a_noop(client: TestClient, owner, instrument) -> None:  # noqa: ANN001
    with SessionLocal() as s:
        before = s.get(Instrument, instrument.id).updated_at
    res = _patch(
        client, owner, instrument, {"model": "DS-252", "capacity": 500.0, "latitude": 23.79}
    )
    assert res.status_code == 200
    assert audit_rows("INSTRUMENT_UPDATED") == []
    with SessionLocal() as s:
        assert s.get(Instrument, instrument.id).updated_at == before
    assert _patch(client, owner, instrument, {}).status_code == 200


def test_bad_path_id_is_422(client: TestClient, owner) -> None:  # noqa: ANN001
    assert client.get("/api/instruments/not-a-uuid", headers=auth_header(owner)).status_code == 422
