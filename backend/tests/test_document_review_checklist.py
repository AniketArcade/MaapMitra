"""Spec 11: document-review checklist snapshot, the review-checklist endpoint, the
DOCUMENT_REVIEW -> DOCUMENTS_DEFICIENT -> SUBMITTED deficiency loop, and the SCHEDULED gate."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.document_review_templates import DOCUMENT_REVIEW_CHECKLIST_TEMPLATE
from app.core.roles import Role
from app.db.session import SessionLocal
from app.models.document_review_checklist import DocumentReviewChecklistItem
from tests.conftest import auth_header
from tests.helpers import audit_rows


def _status(client: TestClient, user, application_id, status: str, note: str | None = None):  # noqa: ANN001, ANN201
    body = {"status": status} | ({"note": note} if note is not None else {})
    return client.patch(
        f"/api/applications/{application_id}/status", json=body, headers=auth_header(user)
    )


def _patch_checklist(client: TestClient, user, application_id, items: list[dict]):  # noqa: ANN001, ANN201
    return client.patch(
        f"/api/applications/{application_id}/review-checklist",
        json={"items": items},
        headers=auth_header(user),
    )


def _snapshot(application_id) -> list[DocumentReviewChecklistItem]:  # noqa: ANN001
    with SessionLocal() as s:
        return list(
            s.scalars(
                select(DocumentReviewChecklistItem).where(
                    DocumentReviewChecklistItem.application_id == application_id
                )
            )
        )


def _check_all(client: TestClient, officer, application_id) -> None:  # noqa: ANN001
    items = _snapshot(application_id)
    res = _patch_checklist(
        client, officer, application_id, [{"item_key": i.item_key, "checked": True} for i in items]
    )
    assert res.status_code == 200, res.text


# ---------------------------------------------------------------------------
# Snapshot on entering DOCUMENT_REVIEW
# ---------------------------------------------------------------------------


def test_snapshot_created_on_entering_document_review(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    items = _snapshot(app.id)
    assert {i.item_key for i in items} == {t.key for t in DOCUMENT_REVIEW_CHECKLIST_TEMPLATE}
    assert all(i.checked is False for i in items)
    assert len(audit_rows("DOCUMENT_REVIEW_STARTED")) == 1

    detail = client.get(f"/api/applications/{app.id}", headers=auth_header(officer)).json()
    assert {i["item_key"] for i in detail["review_checklist"]} == {
        t.key for t in DOCUMENT_REVIEW_CHECKLIST_TEMPLATE
    }
    assert all(i["checked"] is False for i in detail["review_checklist"])


def test_snapshot_survives_template_change_across_a_re_review(
    client: TestClient, make_user, make_application, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A template edit after the first DOCUMENT_REVIEW entry must not retroactively alter an
    already-snapshotted application, even across the deficiency loop's second entry (spec 11,
    mirroring spec 06's inspection-checklist snapshot guarantee)."""
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    app = make_application(owner, status="DOCUMENT_REVIEW", officer=officer)
    labels_before = {i.item_key: i.label for i in _snapshot(app.id)}

    from app.core.document_review_templates import DocumentReviewItemDef

    # Patch the name as looked up inside services/applications.py (the actual call site), not
    # the defining module: the import already bound the original list object there.
    monkeypatch.setattr(
        "app.services.applications.DOCUMENT_REVIEW_CHECKLIST_TEMPLATE",
        [DocumentReviewItemDef("bogus", "Bogus item added after review started")],
    )

    assert (
        _status(
            client, officer, app.id, "DOCUMENTS_DEFICIENT", note="Blurry nameplate photo"
        ).status_code
        == 200
    )
    assert _status(client, owner, app.id, "SUBMITTED").status_code == 200
    assert _status(client, officer, app.id, "DOCUMENT_REVIEW").status_code == 200

    labels_after = {i.item_key: i.label for i in _snapshot(app.id)}
    assert labels_after == labels_before
    assert "bogus" not in labels_after


# ---------------------------------------------------------------------------
# PATCH /applications/{id}/review-checklist
# ---------------------------------------------------------------------------


def test_patch_checklist_persists_partial_updates(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    items = _snapshot(app.id)
    first_key = items[0].item_key

    res = _patch_checklist(client, officer, app.id, [{"item_key": first_key, "checked": True}])
    assert res.status_code == 200, res.text
    body = res.json()
    checked = {i["item_key"]: i["checked"] for i in body["review_checklist"]}
    assert checked[first_key] is True
    assert all(v is False for k, v in checked.items() if k != first_key)


def test_patch_checklist_unknown_item_key_422(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    res = _patch_checklist(
        client, officer, app.id, [{"item_key": "does_not_exist", "checked": True}]
    )
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "items"]


def test_patch_checklist_only_during_document_review(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SUBMITTED")
    res = _patch_checklist(
        client, officer, app.id, [{"item_key": "form_complete", "checked": True}]
    )
    assert res.status_code == 409


@pytest.mark.parametrize(
    "role", [Role.BUSINESS, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN, Role.GATC]
)
def test_patch_checklist_role_rejected(
    client: TestClient, make_user, make_application, role: Role
) -> None:
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    app = make_application(owner, status="DOCUMENT_REVIEW", officer=officer)
    caller = owner if role == Role.BUSINESS else make_user(role)
    res = _patch_checklist(client, caller, app.id, [{"item_key": "form_complete", "checked": True}])
    assert res.status_code == 403


def test_patch_checklist_out_of_jurisdiction_not_found(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    outsider = make_user(Role.LM_OFFICER, district_code="RNC")
    res = _patch_checklist(
        client, outsider, app.id, [{"item_key": "form_complete", "checked": True}]
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# DOCUMENT_REVIEW -> SCHEDULED gate
# ---------------------------------------------------------------------------


def test_scheduling_blocked_until_checklist_complete(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    from app.core import clock

    res = client.patch(
        f"/api/applications/{app.id}/status",
        json={"status": "SCHEDULED", "scheduled_date": clock.today().isoformat()},
        headers=auth_header(officer),
    )
    assert res.status_code == 409
    assert "Document review checklist incomplete" in res.json()["detail"]

    items = _snapshot(app.id)
    # Check all but one: still blocked.
    for item in items[:-1]:
        assert (
            _patch_checklist(
                client, officer, app.id, [{"item_key": item.item_key, "checked": True}]
            ).status_code
            == 200
        )
    res = client.patch(
        f"/api/applications/{app.id}/status",
        json={"status": "SCHEDULED", "scheduled_date": clock.today().isoformat()},
        headers=auth_header(officer),
    )
    assert res.status_code == 409

    # Check the last one: now it succeeds.
    last = items[-1]
    assert (
        _patch_checklist(
            client, officer, app.id, [{"item_key": last.item_key, "checked": True}]
        ).status_code
        == 200
    )
    res = client.patch(
        f"/api/applications/{app.id}/status",
        json={"status": "SCHEDULED", "scheduled_date": clock.today().isoformat()},
        headers=auth_header(officer),
    )
    assert res.status_code == 200, res.text


# ---------------------------------------------------------------------------
# DOCUMENT_REVIEW -> DOCUMENTS_DEFICIENT -> SUBMITTED (the deficiency loop)
# ---------------------------------------------------------------------------


def test_deficient_requires_a_note_lm_officer_only(
    client: TestClient, make_user, make_application
) -> None:
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    app = make_application(owner, status="DOCUMENT_REVIEW", officer=officer)

    for note in (None, "", "too short"):
        res = _status(client, officer, app.id, "DOCUMENTS_DEFICIENT", note=note)
        assert res.status_code == 422
        assert res.json()["detail"][0]["loc"] == ["body", "note"]

    # Wrong role.
    assert (
        _status(
            client, owner, app.id, "DOCUMENTS_DEFICIENT", note="Missing previous certificate"
        ).status_code
        == 403
    )

    res = _status(
        client, officer, app.id, "DOCUMENTS_DEFICIENT", note="Missing previous certificate photo"
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "DOCUMENTS_DEFICIENT"
    assert res.json()["history"][-1]["note"] == "Missing previous certificate photo"


def test_business_can_resubmit_deficient_application(
    client: TestClient, make_user, make_application
) -> None:
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    app = make_application(owner, status="DOCUMENTS_DEFICIENT", officer=officer)

    # Officer (or anyone but the owning business) cannot resubmit.
    assert _status(client, officer, app.id, "SUBMITTED").status_code == 403

    res = _status(client, owner, app.id, "SUBMITTED")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "SUBMITTED"


def test_deficient_is_not_terminal_and_reentering_review_resets_checklist(
    client: TestClient, make_user, make_application
) -> None:
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    app = make_application(owner, status="DOCUMENT_REVIEW", officer=officer)
    _check_all(client, officer, app.id)
    before_ids = {i.id for i in _snapshot(app.id)}

    assert (
        _status(
            client, officer, app.id, "DOCUMENTS_DEFICIENT", note="Blurry nameplate photo"
        ).status_code
        == 200
    )
    assert _status(client, owner, app.id, "SUBMITTED").status_code == 200
    res = _status(client, officer, app.id, "DOCUMENT_REVIEW")
    assert res.status_code == 200

    after = _snapshot(app.id)
    # Same rows (snapshotted once), reset to unchecked for the new review round.
    assert {i.id for i in after} == before_ids
    assert all(i.checked is False for i in after)

    # And the SCHEDULED gate applies again: not simply carried over from last time.
    from app.core import clock

    res = client.patch(
        f"/api/applications/{app.id}/status",
        json={"status": "SCHEDULED", "scheduled_date": clock.today().isoformat()},
        headers=auth_header(officer),
    )
    assert res.status_code == 409


# ---------------------------------------------------------------------------
# applications/meta
# ---------------------------------------------------------------------------


def test_meta_includes_document_review_checklist(client: TestClient, make_user) -> None:
    body = client.get("/api/applications/meta", headers=auth_header(make_user(Role.GATC))).json()
    assert body["document_review_checklist"] == [
        {"key": i.key, "label": i.label} for i in DOCUMENT_REVIEW_CHECKLIST_TEMPLATE
    ]
