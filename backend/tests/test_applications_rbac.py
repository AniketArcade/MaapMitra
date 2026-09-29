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
    assert upload(client, make_user(role), draft.id).status_code == 403
    assert client.delete(f"/api/documents/{doc_id}", headers=headers).status_code == 403


@pytest.mark.parametrize("role", ALL)
def test_read_endpoints(client: TestClient, make_user, make_application, role: Role) -> None:  # noqa: ANN001
    submitted = make_application(status="SUBMITTED")
    headers = auth_header(make_user(role))
    list_res = client.get("/api/applications", headers=headers)
    get_res = client.get(f"/api/applications/{submitted.id}", headers=headers)
    meta_res = client.get("/api/applications/meta", headers=headers)
    assert meta_res.status_code == 200
    if role == Role.GATC:
        assert (list_res.status_code, get_res.status_code) == (403, 403)
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
    expected = {Role.GATC: 403, Role.BUSINESS: 404}.get(role, 200)
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
    assert [s["value"] for s in body["statuses"]][0] == "DRAFT"
