"""Spec 17 §6.4: GET /admin/state-overview — the state-wise table (Phase 1 substitute for a map).
Sibling to tests/test_admin_certificates.py, which already covers the shared /admin/certificates/*
endpoints this one reuses the same scope_* pattern from."""

from fastapi.testclient import TestClient

from app.core.regions import REGIONS
from app.core.roles import Role
from tests.conftest import auth_header


def test_every_region_present_and_zero_filled_with_no_data(client: TestClient, make_user) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    res = client.get("/api/admin/state-overview", headers=auth_header(admin))
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == len(REGIONS)
    assert {r["state_code"] for r in rows} == set(REGIONS)
    for r in rows:
        assert r["instrument_count"] == 0
        assert r["pending_applications"] == 0
        assert r["certs_valid"] == 0
        assert r["certs_expired"] == 0


def test_super_admin_sees_data_outside_jh_br(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER, state_code="KA", district_code="BU")
    owner = make_user(Role.BUSINESS, org_state="KA", org_district="BU")
    make_instrument(owner, state_code="KA", district_code="BU")
    make_application(
        owner,
        make_instrument(owner, state_code="KA", district_code="BU"),
        status="SUBMITTED",
        officer=officer,
    )

    res = client.get("/api/admin/state-overview", headers=auth_header(admin))
    row = next(r for r in res.json() if r["state_code"] == "KA")
    assert row["instrument_count"] == 2
    assert row["pending_applications"] == 1  # SUBMITTED is non-terminal


def test_pending_applications_counts_non_terminal(
    client: TestClient, make_user, make_instrument, make_application
) -> None:
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    make_application(owner, make_instrument(owner), status="DOCUMENT_REVIEW", officer=officer)

    res = client.get("/api/admin/state-overview", headers=auth_header(admin))
    row = next(r for r in res.json() if r["state_code"] == "JH")
    assert row["pending_applications"] == 1


def test_state_admin_sees_only_own_state_nonzero(
    client: TestClient, make_user, make_instrument
) -> None:
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    owner_jh = make_user(Role.BUSINESS)  # JH/DHN by default
    owner_ka = make_user(Role.BUSINESS, org_state="KA", org_district="BU")
    make_instrument(owner_jh)
    make_instrument(owner_ka, state_code="KA", district_code="BU")

    res = client.get("/api/admin/state-overview", headers=auth_header(state_admin))
    rows = {r["state_code"]: r for r in res.json()}
    assert rows["JH"]["instrument_count"] == 1
    assert rows["KA"]["instrument_count"] == 0


def test_business_officer_gatc_forbidden(client: TestClient, make_user) -> None:
    for role in (Role.BUSINESS, Role.LM_OFFICER, Role.GATC):
        res = client.get("/api/admin/state-overview", headers=auth_header(make_user(role)))
        assert res.status_code == 403
