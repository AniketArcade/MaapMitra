import pytest
from fastapi.testclient import TestClient

from app.core.roles import Role
from tests.conftest import auth_header, instrument_body

READERS = {Role.BUSINESS, Role.LM_OFFICER, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN}


@pytest.mark.parametrize("role", list(Role))
def test_only_business_can_create(client: TestClient, make_user, role: Role) -> None:  # noqa: ANN001
    res = client.post(
        "/api/instruments", json=instrument_body(), headers=auth_header(make_user(role))
    )
    assert res.status_code == (201 if role == Role.BUSINESS else 403)


@pytest.mark.parametrize("role", [r for r in Role if r != Role.BUSINESS])
def test_non_business_cannot_update_or_delete(
    client: TestClient,
    make_user,
    make_instrument,
    role: Role,  # noqa: ANN001
) -> None:
    instrument = make_instrument(make_user(Role.BUSINESS))
    headers = auth_header(make_user(role))
    url = f"/api/instruments/{instrument.id}"
    assert client.patch(url, json={"model": "X"}, headers=headers).status_code == 403
    assert client.delete(url, headers=headers).status_code == 403


def test_owner_can_update_and_delete(client: TestClient, make_user, make_instrument) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    url = f"/api/instruments/{instrument.id}"
    assert client.patch(url, json={"model": "X"}, headers=auth_header(owner)).status_code == 200
    assert client.delete(url, headers=auth_header(owner)).status_code == 204


@pytest.mark.parametrize("role", list(Role))
def test_list_and_get_by_role(client: TestClient, make_user, make_instrument, role: Role) -> None:  # noqa: ANN001
    instrument = make_instrument(make_user(Role.BUSINESS))
    headers = auth_header(make_user(role))
    list_res = client.get("/api/instruments", headers=headers)
    get_res = client.get(f"/api/instruments/{instrument.id}", headers=headers)
    if role == Role.GATC:
        assert (list_res.status_code, get_res.status_code) == (403, 403)
    elif role == Role.BUSINESS:  # a different org: empty list, 404
        assert list_res.status_code == 200 and list_res.json()["total"] == 0
        assert get_res.status_code == 404
    else:
        assert role in READERS
        assert list_res.status_code == 200 and get_res.status_code == 200


@pytest.mark.parametrize("role", list(Role))
def test_meta_for_any_logged_in_role(client: TestClient, make_user, role: Role) -> None:  # noqa: ANN001
    res = client.get("/api/instruments/meta", headers=auth_header(make_user(role)))
    assert res.status_code == 200
    body = res.json()
    scale = next(t for t in body["types"] if t["value"] == "WEIGHING_SCALE")
    assert scale["units"] == ["mg", "g", "kg", "t"]
    jh = next(r for r in body["regions"] if r["state_code"] == "JH")
    assert {"DHN", "RNC", "BKR"} <= {d["code"] for d in jh["districts"]}
    assert body["accuracy_classes"] == ["I", "II", "III", "IIII"]


def test_meta_requires_login(client: TestClient) -> None:
    assert client.get("/api/instruments/meta").status_code == 401
    assert client.get("/api/instruments").status_code == 401
