"""Org isolation, draft invisibility for officials, and jurisdiction."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Application, User
from app.services.scoping import scope_applications
from tests.conftest import PDF_BYTES, auth_header, upload


def test_business_cannot_touch_other_orgs_application(
    client: TestClient,
    make_user,
    make_application,  # noqa: ANN001
) -> None:
    a, b = make_user(Role.BUSINESS), make_user(Role.BUSINESS)
    app_b = make_application(b)
    headers = auth_header(a)
    url = f"/api/applications/{app_b.id}"
    assert client.get("/api/applications", headers=headers).json()["total"] == 0
    for res in (
        client.get(url, headers=headers),
        client.patch(url, json={"business_notes": "x"}, headers=headers),
        client.patch(f"{url}/status", json={"status": "SUBMITTED"}, headers=headers),
        client.delete(url, headers=headers),
        upload(client, a, app_b.id),
    ):
        assert res.status_code == 404, res.text
    with SessionLocal() as s:
        row = s.get(Application, app_b.id)
        assert row is not None and row.status == "DRAFT" and row.business_notes is None


def test_business_cannot_reach_other_orgs_documents(
    client: TestClient,
    make_user,
    make_application,  # noqa: ANN001
) -> None:
    a, b = make_user(Role.BUSINESS), make_user(Role.BUSINESS)
    app_b = make_application(b)
    doc_id = upload(client, b, app_b.id).json()["id"]
    assert client.get(f"/api/documents/{doc_id}/url", headers=auth_header(a)).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=auth_header(a)).status_code == 404
    assert client.get(f"/api/documents/{doc_id}/url", headers=auth_header(b)).status_code == 200


def test_officials_never_see_drafts(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    draft = make_application(owner, instrument)
    doc_id = upload(client, owner, draft.id, data=PDF_BYTES).json()["id"]
    officer = make_user(Role.LM_OFFICER)
    headers = auth_header(officer)
    assert client.get("/api/applications", headers=headers).json()["total"] == 0
    assert client.get(f"/api/applications/{draft.id}", headers=headers).status_code == 404
    assert client.get(f"/api/documents/{doc_id}/url", headers=headers).status_code == 404
    inst = client.get(f"/api/instruments/{instrument.id}", headers=headers).json()
    assert inst["active_application"] is None
    owner_view = client.get(f"/api/instruments/{instrument.id}", headers=auth_header(owner)).json()
    assert owner_view["active_application"]["status"] == "DRAFT"

    # After submit it appears for the officer
    upload(client, owner, draft.id, document_type="INSTRUMENT_PHOTO")
    res = client.patch(
        f"/api/applications/{draft.id}/status",
        json={"status": "SUBMITTED"},
        headers=auth_header(owner),
    )
    assert res.status_code == 200, res.text
    assert client.get("/api/applications", headers=headers).json()["total"] == 1
    assert client.get(f"/api/documents/{doc_id}/url", headers=headers).status_code == 200
    inst = client.get(f"/api/instruments/{instrument.id}", headers=headers).json()
    assert inst["active_application"]["status"] == "SUBMITTED"


@pytest.fixture
def regional(make_user, make_instrument, make_application):  # noqa: ANN001, ANN201
    owner = make_user(Role.BUSINESS)
    out = {}
    for key, state, district in (("dhn", "JH", "DHN"), ("rnc", "JH", "RNC"), ("pat", "BR", "PAT")):
        instrument = make_instrument(owner, state_code=state, district_code=district)
        out[key] = make_application(owner, instrument, status="SUBMITTED")
    return out


def _visible(client: TestClient, user: User) -> set[str]:
    items = client.get("/api/applications", headers=auth_header(user)).json()["items"]
    return {f"{i['state_code']}/{i['district_code']}" for i in items}


def test_jurisdiction(client: TestClient, make_user, regional) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)  # JH / DHN
    assert _visible(client, officer) == {"JH/DHN"}
    for key in ("rnc", "pat"):
        assert (
            client.get(
                f"/api/applications/{regional[key].id}", headers=auth_header(officer)
            ).status_code
            == 404
        )
    assert _visible(client, make_user(Role.STATE_ADMIN)) == {"JH/DHN", "JH/RNC"}
    assert _visible(client, make_user(Role.DISTRICT_ADMIN, district_code="RNC")) == {"JH/RNC"}
    assert _visible(client, make_user(Role.SUPER_ADMIN)) == {"JH/DHN", "JH/RNC", "BR/PAT"}


@pytest.mark.parametrize(
    "user",
    [
        User(role=Role.LM_OFFICER, state_code=None, district_code=None),
        User(role=Role.DISTRICT_ADMIN, state_code="JH", district_code=None),
        User(role=Role.STATE_ADMIN, state_code=None),
        User(role=Role.BUSINESS, organization_id=None),
        User(role=Role.GATC),
    ],
)
def test_scope_fails_closed(regional, user: User) -> None:  # noqa: ANN001
    with SessionLocal() as s:
        assert s.scalars(scope_applications(select(Application), user)).all() == []
