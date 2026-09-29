from fastapi.testclient import TestClient

from app.core.roles import Role
from tests.conftest import auth_header


def _patch(client: TestClient, owner, instrument, body: dict):  # noqa: ANN001, ANN202
    return client.patch(f"/api/instruments/{instrument.id}", json=body, headers=auth_header(owner))


def test_identity_and_location_locked_while_active(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    make_application(owner, instrument, status="SUBMITTED")
    for body in (
        {"serial_number": "NEW-1"},
        {"capacity": 600},
        {"model": "X"},
        {"state_code": "JH", "district_code": "RNC"},
    ):
        res = _patch(client, owner, instrument, body)
        assert res.status_code == 409, body
        assert "application in progress" in res.json()["detail"]
        assert "Delete the draft" not in res.json()["detail"]
    assert _patch(client, owner, instrument, {"address": "New shop"}).status_code == 200
    assert (
        _patch(client, owner, instrument, {"latitude": 23.8, "longitude": 86.4}).status_code == 200
    )


def test_draft_lock_message_hints_at_deleting_the_draft(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    make_application(owner, instrument)
    res = _patch(client, owner, instrument, {"serial_number": "NEW-1"})
    assert res.status_code == 409 and "Delete the draft to edit them." in res.json()["detail"]


def test_lock_lifts_after_rejection(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    make_application(owner, instrument, status="REJECTED")
    assert _patch(client, owner, instrument, {"serial_number": "NEW-1"}).status_code == 200


def test_delete_blocked_by_any_application(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    make_application(owner, instrument, status="REJECTED")  # terminal still blocks
    headers = auth_header(owner)
    res = client.delete(f"/api/instruments/{instrument.id}", headers=headers)
    assert (res.status_code, res.json()["detail"]) == (
        409,
        "This instrument has applications and can't be deleted",
    )
    # The session stayed usable and nothing was deleted
    assert client.get(f"/api/instruments/{instrument.id}", headers=headers).status_code == 200


def test_active_application_on_instrument_out(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    headers = auth_header(owner)
    assert (
        client.get(f"/api/instruments/{instrument.id}", headers=headers).json()[
            "active_application"
        ]
        is None
    )
    app = make_application(owner, instrument, status="SUBMITTED")
    ref = client.get(f"/api/instruments/{instrument.id}", headers=headers).json()[
        "active_application"
    ]
    assert ref == {
        "id": str(app.id),
        "application_number": app.application_number,
        "status": "SUBMITTED",
    }
    listed = client.get("/api/instruments", headers=headers).json()["items"][0]
    assert listed["active_application"]["id"] == str(app.id)
