import pytest
from fastapi.testclient import TestClient

from app.core.roles import Role
from tests.conftest import auth_header, upload

ALL = list(Role)
READERS = {Role.BUSINESS, Role.LM_OFFICER, Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN}


@pytest.mark.parametrize("role", ALL)
def test_create(client: TestClient, make_user, make_instrument, role: Role) -> None:  # noqa: ANN001
    user = make_user(role)
    owner = user if role == Role.BUSINESS else make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    body = {"instrument_id": str(instrument.id), "application_type": "VERIFICATION"}
    res = client.post("/api/applications", json=body, headers=auth_header(user))
    assert res.status_code == (201 if role == Role.BUSINESS else 403)


@pytest.mark.parametrize("role", [r for r in ALL if r != Role.BUSINESS])
def test_owner_only_endpoints(client: TestClient, make_user, make_application, role: Role) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    draft = make_application(owner)
    doc_id = upload(client, owner, draft.id).json()["id"]
    headers = auth_header(make_user(role))
    url = f"/api/applications/{draft.id}"
    assert client.patch(url, json={"business_notes": "x"}, headers=headers).status_code == 403
    assert client.delete(url, headers=headers).status_code == 403
    # LM_OFFICER and GATC are both admitted at the router (they upload inspection evidence,
    # spec 06/20), but a DRAFT application has no Inspection row yet -- scope_applications hides
    # it from LM_OFFICER entirely, and GATC's own EXISTS-based scope can never match either (no
    # Inspection to match against) -> 404 for both, not 403. Every other non-BUSINESS role is
    # still blocked at the router itself -> 403.
    expected = 404 if role in (Role.LM_OFFICER, Role.GATC) else 403
    assert upload(client, make_user(role), draft.id).status_code == expected
    assert client.delete(f"/api/documents/{doc_id}", headers=headers).status_code == expected


@pytest.mark.parametrize("role", ALL)
def test_read_endpoints(client: TestClient, make_user, make_application, role: Role) -> None:  # noqa: ANN001
    submitted = make_application(status="SUBMITTED")
    headers = auth_header(make_user(role))
    list_res = client.get("/api/applications", headers=headers)
    get_res = client.get(f"/api/applications/{submitted.id}", headers=headers)
    meta_res = client.get("/api/applications/meta", headers=headers)
    assert meta_res.status_code == 200
    if role == Role.GATC:
        # Spec 20: GATC is now a Reader too, but scope_applications' GATC branch still narrows
        # to nothing for an unassigned user -- 200/empty, 404 on the single-item get, never 403.
        assert list_res.status_code == 200 and list_res.json()["total"] == 0
        assert get_res.status_code == 404
    elif role == Role.BUSINESS:  # another org
        assert list_res.json()["total"] == 0 and get_res.status_code == 404
    else:
        assert role in READERS and list_res.json()["total"] == 1 and get_res.status_code == 200


@pytest.mark.parametrize("role", ALL)
def test_document_url(client: TestClient, make_user, make_application, role: Role) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    submitted = make_application(owner, status="SUBMITTED")
    doc_id = client.get(f"/api/applications/{submitted.id}", headers=auth_header(owner)).json()[
        "documents"
    ][0]["id"]
    res = client.get(f"/api/documents/{doc_id}/url", headers=auth_header(make_user(role)))
    # Spec 20: GATC is now a Reader too; an unassigned GATC user's scope still excludes this
    # application's documents entirely -> 404, same "out of scope" shape as a different BUSINESS.
    expected = 404 if role in (Role.BUSINESS, Role.GATC) else 200
    assert res.status_code == expected


def test_meta(client: TestClient, make_user) -> None:  # noqa: ANN001
    assert client.get("/api/applications/meta").status_code == 401
    body = client.get("/api/applications/meta", headers=auth_header(make_user(Role.GATC))).json()
    ver = next(t for t in body["application_types"] if t["value"] == "VERIFICATION")
    assert ver["required_documents"] == ["PROOF_OF_OWNERSHIP", "INSTRUMENT_PHOTO"]
    assert body["limits"] == {
        "max_file_bytes": 10_485_760,
        "max_documents": 10,
        "allowed_content_types": ["application/pdf", "image/jpeg", "image/png"],
    }
    assert [s["value"] for s in body["statuses"]] == [
        "DRAFT",
        "SUBMITTED",
        "DOCUMENT_REVIEW",
        "DOCUMENTS_DEFICIENT",
        "SCHEDULED",
        "INSPECTION",
        "APPROVED",
        "REJECTED",
        "CERTIFICATE_ISSUED",
    ]
