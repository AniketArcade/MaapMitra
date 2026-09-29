import re
import threading

from fastapi.testclient import TestClient

from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Application
from tests.conftest import BASE_URL, auth_header, upload
from tests.helpers import audit_rows

NUMBER_RE = re.compile(r"^APP-\d{4}-\d{6,}$")


def _create(client: TestClient, owner, instrument, **extra):  # noqa: ANN001, ANN202
    body = {"instrument_id": str(instrument.id), "application_type": "VERIFICATION"} | extra
    return client.post("/api/applications", json=body, headers=auth_header(owner))


def test_create(client: TestClient, make_user, make_instrument) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner, state_code="JH", district_code="RNC")
    res = _create(client, owner, instrument, business_notes="  Shop scale  ")
    assert res.status_code == 201, res.text
    body = res.json()
    assert NUMBER_RE.match(body["application_number"])
    assert body["status"] == "DRAFT" and body["business_notes"] == "Shop scale"
    assert (body["state_code"], body["district_code"]) == ("JH", "RNC")
    assert body["instrument"]["instrument_uid"] == instrument.instrument_uid
    assert body["organization_id"] == str(owner.organization_id)
    rows = audit_rows("APPLICATION_CREATED")
    assert len(rows) == 1 and rows[0].organization_id == owner.organization_id


def test_create_validation(client: TestClient, make_user, make_instrument) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    assert _create(client, owner, instrument, application_type="RENEWAL").status_code == 422
    assert _create(client, owner, instrument, status="SUBMITTED").status_code == 422
    assert _create(client, owner, instrument, business_notes="x" * 1001).status_code == 422
    other = make_instrument(make_user(Role.BUSINESS))
    assert _create(client, owner, other).status_code == 404


def test_one_active_application_per_instrument(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    assert _create(client, owner, instrument).status_code == 201
    res = _create(client, owner, instrument)
    assert (res.status_code, res.json()["detail"]) == (
        409,
        "This instrument already has an application in progress",
    )


def test_new_application_allowed_after_rejection(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    make_application(owner, instrument, status="REJECTED")
    assert _create(client, owner, instrument).status_code == 201


def test_concurrent_creates_one_wins(app, make_user, make_instrument) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    statuses: list[int] = []
    barrier = threading.Barrier(2)

    def go() -> None:
        c = TestClient(app, base_url=BASE_URL)
        barrier.wait()
        statuses.append(_create(c, owner, instrument).status_code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [201, 409]


def test_patch_draft(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    app = make_application(owner)
    url, headers = f"/api/applications/{app.id}", auth_header(owner)
    res = client.patch(
        url, json={"application_type": "RE_VERIFICATION", "business_notes": "n"}, headers=headers
    )
    assert res.status_code == 200 and res.json()["application_type"] == "RE_VERIFICATION"
    rows = audit_rows("APPLICATION_UPDATED")
    assert rows[0].details["changes"]["application_type"] == ["VERIFICATION", "RE_VERIFICATION"]
    # Empty diff: 200, no audit row, updated_at unchanged
    with SessionLocal() as s:
        before = s.get(Application, app.id).updated_at
    assert client.patch(url, json={"business_notes": "n"}, headers=headers).status_code == 200
    assert len(audit_rows("APPLICATION_UPDATED")) == 1
    with SessionLocal() as s:
        assert s.get(Application, app.id).updated_at == before
    assert (
        client.patch(url, json={"business_notes": None}, headers=headers).json()["business_notes"]
        is None
    )
    assert client.patch(url, json={"application_type": None}, headers=headers).status_code == 422
    assert client.patch(url, json={"status": "SUBMITTED"}, headers=headers).status_code == 422


def test_patch_and_delete_only_while_draft(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    app = make_application(owner, status="SUBMITTED")
    url, headers = f"/api/applications/{app.id}", auth_header(owner)
    assert client.patch(url, json={"business_notes": "x"}, headers=headers).status_code == 409
    assert client.delete(url, headers=headers).status_code == 409


def test_delete_draft_removes_documents_and_objects(
    client: TestClient,
    make_user,
    make_application,
    storage,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    app = make_application(owner)
    upload(client, owner, app.id, "PROOF_OF_OWNERSHIP")
    upload(client, owner, app.id, "INSTRUMENT_PHOTO")
    assert len(storage.objects) == 2
    res = client.delete(f"/api/applications/{app.id}", headers=auth_header(owner))
    assert res.status_code == 204
    assert storage.objects == {}
    assert client.get(f"/api/applications/{app.id}", headers=auth_header(owner)).status_code == 404
    rows = audit_rows("APPLICATION_DELETED")
    assert len(rows) == 1 and rows[0].details["documents_deleted"] == 2


def test_list_search_filter_and_paging(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    apps = [
        make_application(owner, make_instrument(owner, serial_number=f"S-{i}")) for i in range(3)
    ]
    make_application(owner, make_instrument(owner, serial_number="SUB_1"), status="SUBMITTED")
    headers = auth_header(owner)

    def get(**params):  # noqa: ANN202, ANN003
        return client.get("/api/applications", params=params, headers=headers).json()

    assert get()["total"] == 4
    assert get(status="SUBMITTED")["total"] == 1
    assert get(status="DRAFT")["total"] == 3
    assert get(q=apps[0].application_number)["total"] == 1
    assert get(q="s-1")["items"][0]["instrument"]["serial_number"] == "S-1"
    assert get(q="%")["total"] == 0
    assert get(q="B_1")["total"] == 1  # literal underscore matches only SUB_1
    assert get(instrument_id=str(apps[1].instrument_id))["total"] == 1
    page1, page2 = get(page=1, page_size=3), get(page=2, page_size=3)
    ids = [i["id"] for i in page1["items"] + page2["items"]]
    assert len(ids) == 4 and len(set(ids)) == 4
    assert client.get("/api/applications?page_size=101", headers=headers).status_code == 422
    assert client.get("/api/applications?status=NOPE", headers=headers).status_code == 422
