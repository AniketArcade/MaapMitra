"""Org isolation (testing priority 1) and official jurisdiction."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Instrument, User
from app.services.scoping import scope_instruments
from tests.conftest import auth_header


@pytest.fixture
def two_orgs(make_user, make_instrument):  # noqa: ANN001, ANN201
    a = make_user(Role.BUSINESS, email="a@biz.demo")
    b = make_user(Role.BUSINESS, email="b@biz.demo")
    return a, b, make_instrument(a, serial_number="A-1"), make_instrument(b, serial_number="B-1")


def test_list_only_shows_own_org(client: TestClient, two_orgs) -> None:  # noqa: ANN001
    a, b, ia, ib = two_orgs
    items = client.get("/api/instruments", headers=auth_header(a)).json()["items"]
    assert [i["id"] for i in items] == [str(ia.id)]
    items = client.get("/api/instruments", headers=auth_header(b)).json()["items"]
    assert [i["id"] for i in items] == [str(ib.id)]


def test_other_orgs_instrument_is_404_for_get_patch_delete(client: TestClient, two_orgs) -> None:  # noqa: ANN001
    a, _, _, ib = two_orgs
    url = f"/api/instruments/{ib.id}"
    for res in (
        client.get(url, headers=auth_header(a)),
        client.patch(url, json={"model": "HACKED"}, headers=auth_header(a)),
        client.delete(url, headers=auth_header(a)),
    ):
        assert res.status_code == 404
        assert res.json() == {"detail": "Instrument not found"}
    with SessionLocal() as s:
        row = s.get(Instrument, ib.id)
        assert row is not None and row.model == "DS-252"


def test_org_id_in_body_is_rejected(client: TestClient, make_user) -> None:  # noqa: ANN001
    a = make_user(Role.BUSINESS)
    b = make_user(Role.BUSINESS)
    body = {
        "instrument_type": "WEIGHING_SCALE",
        "manufacturer": "X",
        "model": "Y",
        "serial_number": "Z1",
        "capacity": 1,
        "capacity_unit": "kg",
        "address": "addr",
        "organization_id": str(b.organization_id),
    }
    assert client.post("/api/instruments", json=body, headers=auth_header(a)).status_code == 422
    with SessionLocal() as s:
        assert s.scalar(select(Instrument)) is None


@pytest.fixture
def regional(make_user, make_instrument):  # noqa: ANN001, ANN201
    owner = make_user(Role.BUSINESS)
    return {
        "dhn": make_instrument(owner, serial_number="DHN-1"),
        "rnc": make_instrument(owner, serial_number="RNC-1", state_code="JH", district_code="RNC"),
        "pat": make_instrument(owner, serial_number="PAT-1", state_code="BR", district_code="PAT"),
    }


def _visible(client: TestClient, user: User) -> set[str]:
    items = client.get("/api/instruments", headers=auth_header(user)).json()["items"]
    return {i["serial_number"] for i in items}


def test_district_officer_sees_only_their_district(client: TestClient, make_user, regional) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)  # JH / DHN
    assert _visible(client, officer) == {"DHN-1"}
    for key in ("rnc", "pat"):
        res = client.get(f"/api/instruments/{regional[key].id}", headers=auth_header(officer))
        assert res.status_code == 404
    res = client.get(f"/api/instruments/{regional['dhn'].id}", headers=auth_header(officer))
    assert res.status_code == 200


def test_district_admin_scope(client: TestClient, make_user, regional) -> None:  # noqa: ANN001
    admin = make_user(Role.DISTRICT_ADMIN, state_code="JH", district_code="RNC")
    assert _visible(client, admin) == {"RNC-1"}


def test_state_admin_sees_their_state(client: TestClient, make_user, regional) -> None:  # noqa: ANN001
    assert _visible(client, make_user(Role.STATE_ADMIN)) == {"DHN-1", "RNC-1"}  # JH


def test_super_admin_sees_all(client: TestClient, make_user, regional) -> None:  # noqa: ANN001
    assert _visible(client, make_user(Role.SUPER_ADMIN)) == {"DHN-1", "RNC-1", "PAT-1"}


def test_scope_filter_narrows_but_never_widens(client: TestClient, make_user, regional) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)  # JH / DHN
    res = client.get("/api/instruments?state_code=BR", headers=auth_header(officer))
    assert res.json()["items"] == []
    res = client.get(
        "/api/instruments?district_code=RNC", headers=auth_header(make_user(Role.STATE_ADMIN))
    )
    assert {i["serial_number"] for i in res.json()["items"]} == {"RNC-1"}


@pytest.mark.parametrize(
    "user",
    [
        User(role=Role.LM_OFFICER, state_code=None, district_code=None),
        User(role=Role.LM_OFFICER, state_code="JH", district_code=None),
        User(role=Role.DISTRICT_ADMIN, state_code=None, district_code="DHN"),
        User(role=Role.STATE_ADMIN, state_code=None),
        User(role=Role.BUSINESS, organization_id=None),
        User(role=Role.GATC),
    ],
)
def test_scope_fails_closed(regional, user: User) -> None:  # noqa: ANN001
    # Bad data the DB constraints normally prevent: the scope must still return nothing.
    with SessionLocal() as s:
        assert s.scalars(scope_instruments(select(Instrument), user)).all() == []
