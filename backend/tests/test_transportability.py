"""Spec 14: instruments.transportable, the office/test-centre vs. on-site verification_mode
snapshot taken on Application at creation, the applications/meta verification_modes entry, and
transportable joining IDENTITY_LOCKED."""

from fastapi.testclient import TestClient

from app.core.application_types import ApplicationStatus as _S
from app.core.instrument_lock import IDENTITY_LOCKED, locked_fields
from app.core.roles import Role
from tests.conftest import auth_header, instrument_body


def _create_instrument(client: TestClient, owner, **overrides):  # noqa: ANN001, ANN201
    return client.post(
        "/api/instruments", json=instrument_body(**overrides), headers=auth_header(owner)
    )


def _create_application(client: TestClient, owner, instrument_id):  # noqa: ANN001, ANN201
    return client.post(
        "/api/applications",
        json={"instrument_id": str(instrument_id), "application_type": "VERIFICATION"},
        headers=auth_header(owner),
    )


def _patch_instrument(client: TestClient, owner, instrument_id, body: dict):  # noqa: ANN001, ANN201
    return client.patch(f"/api/instruments/{instrument_id}", json=body, headers=auth_header(owner))


# ---------------------------------------------------------------------------
# (a) instrument creation: transportable explicit true/false and defaulted
# ---------------------------------------------------------------------------


def test_transportable_defaults_true_when_omitted(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    body = _create_instrument(client, owner).json()
    assert body["transportable"] is True


def test_transportable_explicit_true(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    body = _create_instrument(client, owner, transportable=True).json()
    assert body["transportable"] is True


def test_transportable_explicit_false(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    body = _create_instrument(client, owner, transportable=False).json()
    assert body["transportable"] is False


# ---------------------------------------------------------------------------
# (b) application creation snapshots verification_mode from the instrument's
#     transportable value at that moment
# ---------------------------------------------------------------------------


def test_application_snapshots_office_test_centre_for_transportable(
    client: TestClient, make_user
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = _create_instrument(client, owner, transportable=True).json()
    app_body = _create_application(client, owner, instrument["id"]).json()
    assert app_body["verification_mode"] == "OFFICE_TEST_CENTRE"


def test_application_snapshots_on_site_for_non_transportable(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = _create_instrument(client, owner, transportable=False).json()
    app_body = _create_application(client, owner, instrument["id"]).json()
    assert app_body["verification_mode"] == "ON_SITE"


# ---------------------------------------------------------------------------
# (c) the snapshot is frozen: changing the instrument's transportable later
#     never retroactively changes an already-created application
# ---------------------------------------------------------------------------


def test_changing_transportable_after_application_created_does_not_change_snapshot(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, transportable=True)
    application = make_application(owner, instrument, status="REJECTED")  # terminal: unlocks
    assert application.verification_mode.value == "OFFICE_TEST_CENTRE"

    res = _patch_instrument(client, owner, instrument.id, {"transportable": False})
    assert res.status_code == 200
    assert res.json()["transportable"] is False

    # The existing (now-terminal, unlocked) application's snapshot is untouched.
    detail = client.get(f"/api/applications/{application.id}", headers=auth_header(owner)).json()
    assert detail["verification_mode"] == "OFFICE_TEST_CENTRE"

    # A brand new application for the same (now non-transportable) instrument gets the other mode.
    new_app = _create_application(client, owner, instrument.id).json()
    assert new_app["verification_mode"] == "ON_SITE"


# ---------------------------------------------------------------------------
# (d) applications/meta includes verification_modes
# ---------------------------------------------------------------------------


def test_meta_includes_verification_modes(client: TestClient, make_user) -> None:  # noqa: ANN001
    body = client.get("/api/applications/meta", headers=auth_header(make_user(Role.GATC))).json()
    assert body["verification_modes"] == [
        {"value": "OFFICE_TEST_CENTRE", "label": "Office / test centre"},
        {"value": "ON_SITE", "label": "On-site (in-situ)"},
    ]


# ---------------------------------------------------------------------------
# (e) locked_fields: transportable joins IDENTITY_LOCKED
# ---------------------------------------------------------------------------


def test_transportable_is_identity_locked() -> None:
    assert "transportable" in IDENTITY_LOCKED
    # Matches every other identity field: locked while any non-terminal application exists.
    assert "transportable" in locked_fields(_S.SUBMITTED)
    assert "transportable" not in locked_fields(None)
    assert "transportable" not in locked_fields(_S.REJECTED)


def test_transportable_locked_while_application_in_progress(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, transportable=True)
    make_application(owner, instrument, status="SUBMITTED")

    res = _patch_instrument(client, owner, instrument.id, {"transportable": False})
    assert res.status_code == 409
    assert "application in progress" in res.json()["detail"]


def test_transportable_lock_lifts_after_rejection(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, transportable=True)
    make_application(owner, instrument, status="REJECTED")

    res = _patch_instrument(client, owner, instrument.id, {"transportable": False})
    assert res.status_code == 200
    assert res.json()["transportable"] is False


def test_transportable_cannot_be_set_to_null(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = _create_instrument(client, owner).json()
    res = _patch_instrument(client, owner, instrument["id"], {"transportable": None})
    assert res.status_code == 422
