import pytest
from fastapi.testclient import TestClient

from app.core.application_types import ApplicationStatus
from app.core.instrument_lock import locked_fields
from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Application
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


def _force_status(application_id, status: str) -> None:  # noqa: ANN001
    with SessionLocal() as s:
        s.get(Application, application_id).status = status
        s.commit()


_IDENTITY_ONLY = locked_fields(ApplicationStatus.DRAFT)  # no active-application-specific fields
_IDENTITY_AND_LOCATION = locked_fields(ApplicationStatus.SCHEDULED)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (None, frozenset()),
        ("DRAFT", _IDENTITY_ONLY),
        ("SUBMITTED", _IDENTITY_ONLY),
        ("DOCUMENT_REVIEW", _IDENTITY_ONLY),
        ("SCHEDULED", _IDENTITY_AND_LOCATION),
        ("INSPECTION", _IDENTITY_AND_LOCATION),
        ("APPROVED", _IDENTITY_AND_LOCATION),
        ("REJECTED", frozenset()),
        ("CERTIFICATE_ISSUED", frozenset()),
    ],
)
def test_locked_fields_function(status: str | None, expected: frozenset[str]) -> None:
    active = ApplicationStatus(status) if status else None
    assert locked_fields(active) == expected


def test_location_locked_while_scheduled_and_lifts_after_rejection(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    instrument = make_instrument(owner)
    app = make_application(owner, instrument, status="SCHEDULED", officer=officer)

    for body in ({"address": "New shop"}, {"latitude": 23.8, "longitude": 86.4}):
        res = _patch(client, owner, instrument, body)
        assert res.status_code == 409, body
        assert "inspection is scheduled" in res.json()["detail"]
    # Identity fields are still blocked too (both locks apply simultaneously).
    assert _patch(client, owner, instrument, {"serial_number": "NEW-1"}).status_code == 409

    _force_status(app.id, "APPROVED")
    assert _patch(client, owner, instrument, {"address": "New shop"}).status_code == 409

    _force_status(app.id, "REJECTED")
    assert _patch(client, owner, instrument, {"address": "New shop"}).status_code == 200
    assert (
        _patch(client, owner, instrument, {"latitude": 23.8, "longitude": 86.4}).status_code == 200
    )


def test_instrument_out_reports_locked_fields(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    instrument = make_instrument(owner)
    headers = auth_header(owner)
    no_app = client.get(f"/api/instruments/{instrument.id}", headers=headers).json()
    assert no_app["locked_fields"] == []

    submitted = make_instrument(owner)
    make_application(owner, submitted, status="SUBMITTED")
    body = client.get(f"/api/instruments/{submitted.id}", headers=headers).json()
    assert set(body["locked_fields"]) == locked_fields(ApplicationStatus.SUBMITTED)
    assert "address" not in body["locked_fields"]

    scheduled_instrument = make_instrument(owner)
    make_application(owner, scheduled_instrument, status="SCHEDULED", officer=officer)
    body = client.get(f"/api/instruments/{scheduled_instrument.id}", headers=headers).json()
    assert set(body["locked_fields"]) == locked_fields(ApplicationStatus.SCHEDULED)
    assert "address" in body["locked_fields"]


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
