"""Spec 18 §4: GET /admin/district-overview — the district-level sibling of
tests/test_admin_state_overview.py's state-wise table, one state at a time."""

from fastapi.testclient import TestClient

from app.core.regions import REGIONS
from app.core.roles import Role
from tests.conftest import auth_header


def _issue(client: TestClient, officer, application_id) -> None:  # noqa: ANN001
    res = client.post(
        f"/api/applications/{application_id}/certificate", headers=auth_header(officer)
    )
    assert res.status_code == 200, res.text


def test_super_admin_requires_state_code(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    res = client.get("/api/admin/district-overview", headers=auth_header(admin))
    assert res.status_code == 422, res.text
    assert res.json()["detail"][0]["loc"] == ["body", "state_code"]


def test_super_admin_unknown_state_code_is_404(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    res = client.get(
        "/api/admin/district-overview", params={"state_code": "ZZ"}, headers=auth_header(admin)
    )
    assert res.status_code == 404, res.text


def test_every_district_present_and_zero_filled_with_no_data(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    res = client.get(
        "/api/admin/district-overview", params={"state_code": "JH"}, headers=auth_header(admin)
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == len(REGIONS["JH"]["districts"])
    assert {r["district_code"] for r in rows} == set(REGIONS["JH"]["districts"])
    for r in rows:
        assert r["state_code"] == "JH"
        assert r["instrument_count"] == 0
        assert r["pending_applications"] == 0
        assert r["certs_valid"] == 0
        assert r["certs_expired"] == 0


def test_super_admin_sees_chosen_state_data(client: TestClient, make_user, make_instrument) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    owner_jh = make_user(Role.BUSINESS)  # JH/DHN by default
    owner_ka = make_user(Role.BUSINESS, org_state="KA", org_district="BU")
    make_instrument(owner_jh)
    make_instrument(owner_ka, state_code="KA", district_code="BU")

    res = client.get(
        "/api/admin/district-overview", params={"state_code": "JH"}, headers=auth_header(admin)
    )
    row = next(r for r in res.json() if r["district_code"] == "DHN")
    assert row["instrument_count"] == 1

    res = client.get(
        "/api/admin/district-overview", params={"state_code": "KA"}, headers=auth_header(admin)
    )
    row = next(r for r in res.json() if r["district_code"] == "BU")
    assert row["instrument_count"] == 1


def test_pending_applications_counts_non_terminal(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    make_application(owner, make_instrument(owner), status="DOCUMENT_REVIEW", officer=officer)

    res = client.get(
        "/api/admin/district-overview", params={"state_code": "JH"}, headers=auth_header(admin)
    )
    row = next(r for r in res.json() if r["district_code"] == "DHN")
    assert row["pending_applications"] == 1


def test_cert_counts_are_not_doubled(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    """Guards the scope_certificates() "already joins Certificate -> Application internally"
    invariant — the same bug class caught during spec 17's implementation."""
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    app = make_application(owner, make_instrument(owner), status="APPROVED", officer=officer)
    _issue(client, officer, app.id)

    res = client.get(
        "/api/admin/district-overview", params={"state_code": "JH"}, headers=auth_header(admin)
    )
    row = next(r for r in res.json() if r["district_code"] == "DHN")
    assert row["certs_valid"] == 1
    assert row["certs_expired"] == 0


def test_state_admin_state_code_param_is_ignored_and_forced_to_own_state(
    client: TestClient, make_user, make_instrument
) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    owner = make_user(Role.BUSINESS)  # JH/DHN by default
    make_instrument(owner)

    res = client.get(
        "/api/admin/district-overview",
        params={"state_code": "KA"},
        headers=auth_header(state_admin),
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert {r["state_code"] for r in rows} == {"JH"}
    row = next(r for r in rows if r["district_code"] == "DHN")
    assert row["instrument_count"] == 1


def test_district_admin_gets_own_state_rows_too(client: TestClient, make_user) -> None:
    district_admin = make_user(Role.DISTRICT_ADMIN)  # JH/DHN
    res = client.get("/api/admin/district-overview", headers=auth_header(district_admin))
    assert res.status_code == 200, res.text
    assert {r["state_code"] for r in res.json()} == {"JH"}


def test_business_officer_gatc_forbidden(client: TestClient, make_user) -> None:
    for role in (Role.BUSINESS, Role.LM_OFFICER, Role.GATC):
        res = client.get(
            "/api/admin/district-overview",
            params={"state_code": "JH"},
            headers=auth_header(make_user(role)),
        )
        assert res.status_code == 403
