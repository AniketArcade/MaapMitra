import threading

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Application, ApplicationStatusHistory
from tests.conftest import BASE_URL, auth_header, upload
from tests.helpers import audit_rows, submit_checklist


def _status(  # noqa: ANN201
    client: TestClient,
    user,  # noqa: ANN001
    application_id,  # noqa: ANN001
    status: str,
    note: str | None = None,
    scheduled_date: str | None = None,
):
    body = (
        {"status": status}
        | ({"note": note} if note is not None else {})
        | ({"scheduled_date": scheduled_date} if scheduled_date is not None else {})
    )
    return client.patch(
        f"/api/applications/{application_id}/status", json=body, headers=auth_header(user)
    )


def _history(application_id) -> list[tuple]:  # noqa: ANN001
    with SessionLocal() as s:
        rows = s.scalars(
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id == application_id)
            .order_by(ApplicationStatusHistory.created_at)
        ).all()
        return [(r.from_status, r.to_status, r.note) for r in rows]


def test_happy_path_submit_review_reject(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner, officer = make_user(Role.BUSINESS), make_user(Role.LM_OFFICER)
    app = make_application(owner)
    upload(client, owner, app.id, "PROOF_OF_OWNERSHIP")
    upload(client, owner, app.id, "INSTRUMENT_PHOTO", filename="photo.pdf")

    res = _status(client, owner, app.id, "SUBMITTED")
    assert res.status_code == 200
    assert res.json()["status"] == "SUBMITTED" and res.json()["submitted_at"]
    assert res.json()["allowed_actions"] == []  # owner can't start review

    res = _status(client, officer, app.id, "DOCUMENT_REVIEW")
    assert res.status_code == 200
    assert set(res.json()["allowed_actions"]) == {"REJECTED", "SCHEDULED"}

    res = _status(client, officer, app.id, "REJECTED", note="Invoice is not legible")
    assert res.status_code == 200 and res.json()["status"] == "REJECTED"
    assert [h["to_status"] for h in res.json()["history"]] == [
        "DRAFT",
        "SUBMITTED",
        "DOCUMENT_REVIEW",
        "REJECTED",
    ]
    assert res.json()["history"][-1]["note"] == "Invoice is not legible"
    assert _history(app.id)[-1] == ("DOCUMENT_REVIEW", "REJECTED", "Invoice is not legible")
    assert len(audit_rows("APPLICATION_STATUS_CHANGED")) == 3


def test_owner_sees_submit_action_on_draft(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    app = make_application(owner)
    detail = client.get(f"/api/applications/{app.id}", headers=auth_header(owner)).json()
    assert detail["allowed_actions"] == ["SUBMITTED"]
    assert {
        r["document_type"]: (r["required"], r["satisfied"]) for r in detail["requirements"]
    } == {
        "PROOF_OF_OWNERSHIP": (True, False),
        "INSTRUMENT_PHOTO": (True, False),
        "PREVIOUS_CERTIFICATE": (False, False),
        "MODEL_APPROVAL": (False, False),
        "OTHER": (False, False),
    }


def test_evaluation_order(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner, officer = make_user(Role.BUSINESS), make_user(Role.LM_OFFICER)
    submitted = make_application(owner, status="SUBMITTED")
    # Not an edge -> 409, even for a role that could never take it
    res = _status(client, owner, submitted.id, "APPROVED")
    assert (res.status_code, res.json()["detail"]) == (409, "Invalid status change")
    assert _status(client, officer, submitted.id, "SCHEDULED").status_code == 409
    # Real edge, wrong role -> 403
    assert _status(client, owner, submitted.id, "DOCUMENT_REVIEW").status_code == 403
    assert (
        _status(client, make_user(Role.DISTRICT_ADMIN), submitted.id, "DOCUMENT_REVIEW").status_code
        == 403
    )
    assert (
        _status(client, make_user(Role.SUPER_ADMIN), submitted.id, "DOCUMENT_REVIEW").status_code
        == 403
    )
    assert _status(client, make_user(Role.GATC), submitted.id, "DOCUMENT_REVIEW").status_code == 403
    # Real edge, right role, enabled, but an edge-specific rule blocks it (step 7: checklist not
    # yet submitted)
    inspecting = make_application(owner, status="INSPECTION", officer=officer)
    res = _status(client, officer, inspecting.id, "APPROVED")
    assert (res.status_code, res.json()["detail"]) == (
        409,
        "The inspection checklist must be submitted before approving or rejecting",
    )


def test_certificate_issued_never_via_patch(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    assert _status(client, officer, app.id, "CERTIFICATE_ISSUED").status_code == 409
    with SessionLocal() as s:  # force APPROVED: the system-only edge must still refuse
        s.get(Application, app.id).status = "APPROVED"
        s.commit()
    assert _status(client, officer, app.id, "CERTIFICATE_ISSUED").status_code == 403
    assert (
        _status(client, make_user(Role.SUPER_ADMIN), app.id, "CERTIFICATE_ISSUED").status_code
        == 403
    )


def test_rejected_is_terminal(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="REJECTED", officer=officer)
    for target in ("DRAFT", "SUBMITTED", "DOCUMENT_REVIEW", "APPROVED"):
        assert _status(client, officer, app.id, target).status_code == 409


@pytest.mark.parametrize("note", [None, "", "too short"])
def test_reject_needs_a_reason(client: TestClient, make_user, make_application, note) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    res = _status(client, officer, app.id, "REJECTED", note=note)
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "note"]


def test_note_too_long(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    assert _status(client, officer, app.id, "REJECTED", note="x" * 1001).status_code == 422


def test_submit_requires_documents(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    app = make_application(owner)
    res = _status(client, owner, app.id, "SUBMITTED")
    assert res.status_code == 409
    assert "Purchase invoice" in res.json()["detail"] and "Photo" in res.json()["detail"]
    upload(client, owner, app.id, "PROOF_OF_OWNERSHIP")
    res = _status(client, owner, app.id, "SUBMITTED")
    assert res.status_code == 409 and "Purchase invoice" not in res.json()["detail"]
    upload(client, owner, app.id, "INSTRUMENT_PHOTO")
    assert _status(client, owner, app.id, "SUBMITTED").status_code == 200


def test_re_verification_requirements_differ(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    app = make_application(owner, application_type="RE_VERIFICATION")
    upload(client, owner, app.id, "PROOF_OF_OWNERSHIP")
    upload(client, owner, app.id, "INSTRUMENT_PHOTO")
    res = _status(client, owner, app.id, "SUBMITTED")
    assert res.status_code == 409 and "Previous verification certificate" in res.json()["detail"]
    upload(client, owner, app.id, "PREVIOUS_CERTIFICATE")
    assert _status(client, owner, app.id, "SUBMITTED").status_code == 200


def test_each_transition_writes_one_history_and_audit_row(
    client: TestClient,
    make_user,
    make_application,  # noqa: ANN001
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SUBMITTED")
    before = len(_history(app.id))
    audits = len(audit_rows("APPLICATION_STATUS_CHANGED"))
    assert _status(client, officer, app.id, "DOCUMENT_REVIEW").status_code == 200
    assert len(_history(app.id)) == before + 1
    rows = audit_rows("APPLICATION_STATUS_CHANGED")
    assert len(rows) == audits + 1
    review = [r for r in rows if r.details["to"] == "DOCUMENT_REVIEW"]
    assert len(review) == 1
    assert review[0].details == {"from": "SUBMITTED", "to": "DOCUMENT_REVIEW", "note": None}
    assert review[0].actor_user_id == officer.id
    # A refused transition writes nothing (INSPECTION is never a direct edge from DOCUMENT_REVIEW)
    assert _status(client, officer, app.id, "INSPECTION").status_code == 409
    assert len(_history(app.id)) == before + 1


def test_concurrent_transitions_one_wins(app, make_user, make_application) -> None:  # noqa: ANN001
    officers = [make_user(Role.LM_OFFICER), make_user(Role.LM_OFFICER)]
    submitted = make_application(status="SUBMITTED")
    statuses: list[int] = []
    barrier = threading.Barrier(2)

    def go(i: int) -> None:
        c = TestClient(app, base_url=BASE_URL)
        barrier.wait()
        statuses.append(_status(c, officers[i], submitted.id, "DOCUMENT_REVIEW").status_code)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [200, 409]
    with SessionLocal() as s:
        n = s.scalar(
            select(func.count())
            .select_from(ApplicationStatusHistory)
            .where(
                ApplicationStatusHistory.application_id == submitted.id,
                ApplicationStatusHistory.to_status == "DOCUMENT_REVIEW",
            )
        )
    assert n == 1


# Spec 07: Approve/Reject.


def test_approve_reject_require_submitted_checklist(
    client: TestClient,
    make_user,
    make_application,  # noqa: ANN001
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    for status, note in (("APPROVED", None), ("REJECTED", "Fails the load test badly")):
        res = _status(client, officer, app.id, status, note=note)
        assert (res.status_code, res.json()["detail"]) == (
            409,
            "The inspection checklist must be submitted before approving or rejecting",
        )
    detail = client.get(f"/api/applications/{app.id}", headers=auth_header(officer)).json()
    assert "APPROVED" not in detail["allowed_actions"]
    assert "REJECTED" not in detail["allowed_actions"]


def test_approve_by_non_assigned_officer_succeeds(
    client: TestClient,
    make_user,
    make_application,  # noqa: ANN001
) -> None:
    assigned = make_user(Role.LM_OFFICER)
    reviewer = make_user(Role.LM_OFFICER)  # in-scope, but not the officer who inspected
    app = make_application(status="INSPECTION", officer=assigned)
    submit_checklist(client, assigned, app.inspection.id)

    before_history = len(_history(app.id))
    before_audits = len(audit_rows("APPLICATION_STATUS_CHANGED"))
    res = _status(client, reviewer, app.id, "APPROVED")
    assert res.status_code == 200 and res.json()["status"] == "APPROVED"
    assert len(_history(app.id)) == before_history + 1

    rows = audit_rows("APPLICATION_STATUS_CHANGED")
    assert len(rows) == before_audits + 1
    decision = rows[-1]
    assert decision.details["to"] == "APPROVED"
    assert decision.details["checklist_summary"]["PASS"] > 0
    assert decision.details["checklist_summary"]["FAIL"] == 0

    instrument = client.get(
        f"/api/instruments/{app.instrument.id}", headers=auth_header(reviewer)
    ).json()
    assert "address" in instrument["locked_fields"]  # stays locked through APPROVED


def test_approve_with_no_note_succeeds(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    submit_checklist(client, officer, app.inspection.id)
    assert _status(client, officer, app.id, "APPROVED").status_code == 200
    assert _history(app.id)[-1] == ("INSPECTION", "APPROVED", None)


def test_reject_from_inspection_succeeds_and_unlocks_instrument(
    client: TestClient,
    make_user,
    make_application,  # noqa: ANN001
) -> None:
    officer = make_user(Role.LM_OFFICER)
    reviewer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    submit_checklist(client, officer, app.inspection.id)

    res = _status(client, reviewer, app.id, "REJECTED", note="Fails the load test badly")
    assert res.status_code == 200 and res.json()["status"] == "REJECTED"

    instrument = client.get(
        f"/api/instruments/{app.instrument.id}", headers=auth_header(reviewer)
    ).json()
    assert instrument["locked_fields"] == []  # REJECTED is terminal: fully unlocked


@pytest.mark.parametrize("note", [None, "", "too short"])
def test_reject_from_inspection_needs_a_reason(  # noqa: ANN001
    client: TestClient, make_user, make_application, note
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="INSPECTION", officer=officer)
    submit_checklist(client, officer, app.inspection.id)
    res = _status(client, officer, app.id, "REJECTED", note=note)
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "note"]


def test_approve_reject_role_and_scope(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    app = make_application(owner, status="INSPECTION", officer=officer)
    submit_checklist(client, officer, app.inspection.id)

    # In scope (can see the application) but wrong role -> 403, mirroring test_evaluation_order.
    assert _status(client, owner, app.id, "APPROVED").status_code == 403
    assert _status(client, make_user(Role.DISTRICT_ADMIN), app.id, "APPROVED").status_code == 403
    assert _status(client, make_user(Role.SUPER_ADMIN), app.id, "APPROVED").status_code == 403
    assert _status(client, make_user(Role.GATC), app.id, "APPROVED").status_code == 403

    outsider = make_user(Role.LM_OFFICER, district_code="RNC")
    assert _status(client, outsider, app.id, "APPROVED").status_code == 404
