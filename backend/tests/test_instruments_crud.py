import re
import threading
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Instrument
from tests.conftest import BASE_URL, auth_header, instrument_body
from tests.helpers import audit_rows

UID_RE = re.compile(r"^LM-[A-Z]{2}-[A-Z]{2,4}-\d{6,}$")


def test_create_returns_uid_and_org(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    res = client.post(
        "/api/instruments",
        json=instrument_body(serial_number="XYZ12345"),
        headers=auth_header(owner),
    )
    assert res.status_code == 201
    body = res.json()
    assert UID_RE.match(body["instrument_uid"])
    assert body["instrument_uid"].startswith("LM-JH-DHN-")
    assert body["organization_id"] == str(owner.organization_id)
    assert body["organization_name"] == owner.organization.name
    with SessionLocal() as s:
        assert s.get(Instrument, uuid.UUID(body["id"])).created_by == owner.id


def test_uid_uses_instrument_location_and_is_permanent(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    headers = auth_header(owner)
    body = client.post(
        "/api/instruments",
        json=instrument_body(state_code="BR", district_code="PAT"),
        headers=headers,
    ).json()
    assert body["instrument_uid"].startswith("LM-BR-PAT-")
    moved = client.patch(
        f"/api/instruments/{body['id']}",
        json={"state_code": "JH", "district_code": "RNC"},
        headers=headers,
    ).json()
    assert moved["district_code"] == "RNC"
    assert moved["instrument_uid"] == body["instrument_uid"]


def _parallel(fn, n: int) -> list:  # noqa: ANN001
    results: list = []
    barrier = threading.Barrier(n)

    def run(i: int) -> None:
        barrier.wait()
        results.append(fn(i))

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_concurrent_creates_get_distinct_uids(app, make_user) -> None:  # noqa: ANN001
    headers = auth_header(make_user(Role.BUSINESS))

    def create(i: int):  # noqa: ANN202
        c = TestClient(app, base_url=BASE_URL)
        return c.post(
            "/api/instruments", json=instrument_body(serial_number=f"C-{i}"), headers=headers
        )

    responses = _parallel(create, 10)
    assert [r.status_code for r in responses] == [201] * 10
    uids = {r.json()["instrument_uid"] for r in responses}
    assert len(uids) == 10 and all(UID_RE.match(u) for u in uids)


def test_duplicate_across_orgs_is_409_without_naming_owner(client: TestClient, make_user) -> None:  # noqa: ANN001
    a = make_user(Role.BUSINESS)
    b = make_user(Role.BUSINESS)
    first = instrument_body(manufacturer="Essae", serial_number="XYZ12345")
    assert client.post("/api/instruments", json=first, headers=auth_header(a)).status_code == 201
    dup = instrument_body(manufacturer="ESSAE", serial_number=" xyz12345 ")
    res = client.post("/api/instruments", json=dup, headers=auth_header(b))
    assert res.status_code == 409
    assert "already registered" in res.json()["detail"]
    assert a.organization.name not in res.text
    # a different manufacturer with the same serial is a different instrument
    other = instrument_body(manufacturer="Avery", serial_number="XYZ12345")
    assert client.post("/api/instruments", json=other, headers=auth_header(b)).status_code == 201


def test_duplicate_via_patch_is_409(client: TestClient, make_user, make_instrument) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    make_instrument(owner, serial_number="ONE")
    second = make_instrument(owner, serial_number="TWO")
    res = client.patch(
        f"/api/instruments/{second.id}", json={"serial_number": "one"}, headers=auth_header(owner)
    )
    assert res.status_code == 409


def test_concurrent_duplicate_one_wins(app, make_user) -> None:  # noqa: ANN001
    users = [make_user(Role.BUSINESS), make_user(Role.BUSINESS)]

    def create(i: int) -> int:
        c = TestClient(app, base_url=BASE_URL)
        body = instrument_body(serial_number="RACE-1")
        return c.post("/api/instruments", json=body, headers=auth_header(users[i])).status_code

    assert sorted(_parallel(create, 2)) == [201, 409]


def test_patch_changes_only_sent_fields_and_audits(
    client: TestClient, make_user, make_instrument
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    instrument = make_instrument(owner)
    res = client.patch(
        f"/api/instruments/{instrument.id}",
        json={"model": "DS-300", "capacity": 600},
        headers=auth_header(owner),
    )
    assert res.status_code == 200
    body = res.json()
    assert (body["model"], body["capacity"], body["manufacturer"]) == (
        "DS-300",
        600.0,
        "Essae Teraoka",
    )
    rows = audit_rows("INSTRUMENT_UPDATED")
    assert len(rows) == 1
    assert rows[0].organization_id == owner.organization_id
    assert rows[0].details["changes"] == {
        "model": ["DS-252", "DS-300"],
        "capacity": ["500.000", "600"],
    }


def test_create_and_delete_audit(client: TestClient, make_user) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    headers = auth_header(owner)
    body = client.post("/api/instruments", json=instrument_body(), headers=headers).json()
    created = audit_rows("INSTRUMENT_CREATED")
    assert len(created) == 1 and created[0].organization_id == owner.organization_id
    assert created[0].ip_address == "testclient"

    assert client.delete(f"/api/instruments/{body['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/instruments/{body['id']}", headers=headers).status_code == 404
    deleted = audit_rows("INSTRUMENT_DELETED")
    assert len(deleted) == 1
    assert deleted[0].details == {
        "instrument_uid": body["instrument_uid"],
        "serial_number": body["serial_number"],
    }
    assert deleted[0].entity_id == uuid.UUID(body["id"])


def test_pagination_total_and_stable_order(client: TestClient, make_user, make_instrument) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    for i in range(7):
        make_instrument(owner, serial_number=f"P-{i}")
    headers = auth_header(owner)
    seen: list[str] = []
    for page in (1, 2, 3):
        res = client.get(f"/api/instruments?page={page}&page_size=3", headers=headers).json()
        assert res["total"] == 7 and res["page"] == page and res["page_size"] == 3
        seen += [i["id"] for i in res["items"]]
    assert len(seen) == 7 and len(set(seen)) == 7
    with SessionLocal() as s:
        newest = s.scalars(select(Instrument).order_by(Instrument.created_at.desc())).first()
    assert seen[0] == str(newest.id)
    assert client.get("/api/instruments?page_size=101", headers=headers).status_code == 422
    assert client.get("/api/instruments?page=0", headers=headers).status_code == 422


def test_search(client: TestClient, make_user, make_instrument) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    target = make_instrument(owner, serial_number="XYZ12345")
    make_instrument(owner, serial_number="ABC_999", manufacturer="Avery")
    headers = auth_header(owner)

    def serials(q: str) -> set[str]:
        items = client.get("/api/instruments", params={"q": q}, headers=headers).json()["items"]
        return {i["serial_number"] for i in items}

    assert serials("xyz123") == {"XYZ12345"}
    assert serials(target.instrument_uid.lower()) == {"XYZ12345"}
    assert serials("avery") == {"ABC_999"}
    assert serials("%") == set()  # escaped, not a wildcard
    assert serials("C_9") == {"ABC_999"}  # literal underscore
    assert serials("B_C") == set()  # "_" doesn't match any character
    res = client.get("/api/instruments", params={"q": "x" * 101}, headers=headers)
    assert res.status_code == 422
