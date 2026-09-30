"""Spec 05: DOCUMENT_REVIEW -> SCHEDULED, reschedule, sort=scheduled_asc, and the
instrument address/coordinate lock activated by scheduling."""

import threading
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.core import clock
from app.core.roles import Role
from app.db.session import SessionLocal, engine
from tests.conftest import BASE_URL, auth_header
from tests.helpers import audit_rows

FROZEN = datetime(2026, 10, 14, 20, 0, tzinfo=UTC)  # = 2026-10-15 01:30 IST


@pytest.fixture
def frozen_today(monkeypatch: pytest.MonkeyPatch) -> date:
    monkeypatch.setattr(clock, "now_utc", lambda: FROZEN)
    return clock.today()  # 2026-10-15, per APP_TIMEZONE default Asia/Kolkata


def _schedule(client: TestClient, user, application_id, scheduled_date: str | None):  # noqa: ANN001, ANN201
    body = {"status": "SCHEDULED"} | ({"scheduled_date": scheduled_date} if scheduled_date else {})
    return client.patch(
        f"/api/applications/{application_id}/status", json=body, headers=auth_header(user)
    )


def _reschedule(client: TestClient, user, application_id, scheduled_date: str):  # noqa: ANN001, ANN201
    return client.patch(
        f"/api/applications/{application_id}/inspection",
        json={"scheduled_date": scheduled_date},
        headers=auth_header(user),
    )


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


def test_schedule_success(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    d = clock.today().isoformat()
    res = _schedule(client, officer, app.id, d)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "SCHEDULED"
    assert body["inspection"]["scheduled_date"] == d
    assert body["inspection"]["assigned_officer_name"] == officer.full_name
    assert body["inspection"]["id"]  # step 6: the frontend needs it to reach /inspections/{id}
    assert body["scheduled_date"] == d
    assert body["can_reschedule"] is True

    with SessionLocal() as s:
        from app.models.inspection import Inspection

        rows = s.scalars(select(Inspection).where(Inspection.application_id == app.id)).all()
    assert len(rows) == 1
    assert rows[0].assigned_officer_id == officer.id


def test_schedule_writes_one_of_each_row(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    res = _schedule(client, officer, app.id, clock.today().isoformat())
    assert res.status_code == 200
    history = [h for h in res.json()["history"] if h["to_status"] == "SCHEDULED"]
    assert len(history) == 1 and str(clock.today()) in history[0]["note"]
    assert len(audit_rows("INSPECTION_SCHEDULED")) == 1
    status_changed = [
        r for r in audit_rows("APPLICATION_STATUS_CHANGED") if r.details["to"] == "SCHEDULED"
    ]
    assert len(status_changed) == 1


def test_schedule_missing_date(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    res = _schedule(client, officer, app.id, None)
    assert res.status_code == 422


def test_schedule_date_rejected_on_other_targets(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    res = client.patch(
        f"/api/applications/{app.id}/status",
        json={"status": "REJECTED", "note": "Not compliant", "scheduled_date": "2026-10-15"},
        headers=auth_header(officer),
    )
    assert res.status_code == 422


def test_schedule_date_boundaries(
    client: TestClient, make_user, make_application, frozen_today: date
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)

    def app_() -> object:
        return make_application(status="DOCUMENT_REVIEW", officer=officer)

    def sched(delta_days: int) -> int:
        d = (frozen_today + timedelta(days=delta_days)).isoformat()
        return _schedule(client, officer, app_().id, d).status_code

    assert sched(-1) == 422
    assert sched(0) == 200
    assert sched(180) == 200
    assert sched(181) == 422


def test_schedule_role_and_scope(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    dhn_officer = make_user(Role.LM_OFFICER)
    app = make_application(owner, status="DOCUMENT_REVIEW", officer=dhn_officer)
    d = clock.today().isoformat()
    assert _schedule(client, owner, app.id, d).status_code == 403
    for role in (Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN, Role.GATC):
        assert _schedule(client, make_user(role), app.id, d).status_code == 403
    rnc_officer = make_user(Role.LM_OFFICER, district_code="RNC")
    assert _schedule(client, rnc_officer, app.id, d).status_code == 404


def test_concurrent_schedule_one_wins(app, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    in_review = make_application(status="DOCUMENT_REVIEW", officer=officer)
    d = clock.today().isoformat()
    statuses: list[int] = []
    barrier = threading.Barrier(2)

    def go() -> None:
        c = TestClient(app, base_url=BASE_URL)
        barrier.wait()
        statuses.append(_schedule(c, officer, in_review.id, d).status_code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == [200, 409]
    with SessionLocal() as s:
        from app.models.inspection import Inspection

        rows = s.scalars(select(Inspection).where(Inspection.application_id == in_review.id)).all()
    assert len(rows) == 1


def test_schedule_races_instrument_address_patch(
    app, make_user, make_instrument, make_application
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    instrument = make_instrument(owner)
    in_review = make_application(owner, instrument, status="DOCUMENT_REVIEW", officer=officer)
    d = clock.today().isoformat()
    results: dict[str, int] = {}
    barrier = threading.Barrier(2)

    def do_schedule() -> None:
        c = TestClient(app, base_url=BASE_URL)
        barrier.wait()
        results["schedule"] = _schedule(c, officer, in_review.id, d).status_code

    def do_patch() -> None:
        c = TestClient(app, base_url=BASE_URL)
        barrier.wait()
        results["patch"] = c.patch(
            f"/api/instruments/{instrument.id}",
            json={"address": "Moved shop"},
            headers=auth_header(owner),
        ).status_code

    t1, t2 = threading.Thread(target=do_schedule), threading.Thread(target=do_patch)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results["schedule"] == 200
    # Whichever order they serialised in, the PATCH never commits an address change
    # that lands *after* the instrument is SCHEDULED-locked.
    with SessionLocal() as s:
        from app.models.instrument import Instrument

        current_address = s.get(Instrument, instrument.id).address
    if results["patch"] == 200:
        assert current_address == "Moved shop"
    else:
        assert results["patch"] == 409
        assert current_address == instrument.address


# ---------------------------------------------------------------------------
# Reschedule
# ---------------------------------------------------------------------------


def test_reschedule_success(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SCHEDULED", officer=officer)
    old_date = clock.today().isoformat()
    new_date = (clock.today() + timedelta(days=5)).isoformat()
    res = _reschedule(client, officer, app.id, new_date)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["inspection"]["scheduled_date"] == new_date
    assert body["inspection"]["assigned_officer_name"] == officer.full_name  # unchanged assignee

    rows = audit_rows("INSPECTION_RESCHEDULED")
    assert len(rows) == 1
    assert rows[0].details == {"changes": {"scheduled_date": [old_date, new_date]}}


def test_reschedule_same_date_is_a_noop(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SCHEDULED", officer=officer)
    same_date = clock.today().isoformat()
    res = _reschedule(client, officer, app.id, same_date)
    assert res.status_code == 200
    assert len(audit_rows("INSPECTION_RESCHEDULED")) == 0


def test_reschedule_invalid_date(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SCHEDULED", officer=officer)
    past = (clock.today() - timedelta(days=1)).isoformat()
    assert _reschedule(client, officer, app.id, past).status_code == 422


def test_reschedule_requires_scheduled_status(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="DOCUMENT_REVIEW", officer=officer)
    res = _reschedule(client, officer, app.id, clock.today().isoformat())
    assert res.status_code == 409


def test_reschedule_role_and_scope(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SCHEDULED", officer=officer)
    new_date = (clock.today() + timedelta(days=1)).isoformat()
    owner_headers_user = make_user(Role.BUSINESS)
    assert _reschedule(client, owner_headers_user, app.id, new_date).status_code == 403
    for role in (Role.DISTRICT_ADMIN, Role.STATE_ADMIN, Role.SUPER_ADMIN, Role.GATC):
        assert _reschedule(client, make_user(role), app.id, new_date).status_code == 403
    rnc_officer = make_user(Role.LM_OFFICER, district_code="RNC")
    assert _reschedule(client, rnc_officer, app.id, new_date).status_code == 404


def test_can_reschedule_flag(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    scheduled = make_application(owner, status="SCHEDULED", officer=officer)
    in_review = make_application(owner, status="DOCUMENT_REVIEW", officer=officer)

    def detail(app_id, user):  # noqa: ANN001, ANN202
        return client.get(f"/api/applications/{app_id}", headers=auth_header(user)).json()

    assert detail(scheduled.id, officer)["can_reschedule"] is True
    assert detail(scheduled.id, owner)["can_reschedule"] is False  # business can't reschedule
    assert detail(in_review.id, officer)["can_reschedule"] is False  # not SCHEDULED yet


# ---------------------------------------------------------------------------
# Reads: inspection visibility, stats consistency, sort
# ---------------------------------------------------------------------------


def test_inspection_visible_to_owner_and_officer_not_other_orgs(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    officer = make_user(Role.LM_OFFICER)
    other_business = make_user(Role.BUSINESS)
    app = make_application(owner, status="SCHEDULED", officer=officer)

    owner_view = client.get(f"/api/applications/{app.id}", headers=auth_header(owner)).json()
    officer_view = client.get(f"/api/applications/{app.id}", headers=auth_header(officer)).json()
    assert owner_view["inspection"]["assigned_officer_name"] == officer.full_name
    assert officer_view["inspection"]["assigned_officer_name"] == officer.full_name

    other_res = client.get(f"/api/applications/{app.id}", headers=auth_header(other_business))
    assert other_res.status_code == 404


def test_stats_and_status_filter_reflect_scheduled_immediately(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="SCHEDULED", officer=officer)
    stats = client.get("/api/applications/stats", headers=auth_header(officer)).json()
    assert stats["by_status"]["SCHEDULED"] == 1
    listed = client.get("/api/applications?status=SCHEDULED", headers=auth_header(officer)).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == str(app.id)


def test_sort_scheduled_asc(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    # Three SCHEDULED applications with distinct dates, created in a shuffled order.
    with_inspection = []
    for offset in (10, 1, 5):
        app = make_application(owner, status="DOCUMENT_REVIEW", officer=officer)
        d = (clock.today() + timedelta(days=offset)).isoformat()
        res = _schedule(client, officer, app.id, d)
        assert res.status_code == 200
        with_inspection.append((app.id, d))
    no_inspection = make_application(owner, status="SUBMITTED")

    res = client.get(
        "/api/applications?sort=scheduled_asc&page_size=50", headers=auth_header(officer)
    )
    assert res.status_code == 200
    items = res.json()["items"]
    dated = [i for i in items if i["scheduled_date"]]
    assert [i["scheduled_date"] for i in dated] == sorted(d for _, d in with_inspection)
    # Applications without an inspection sort last.
    assert items[-1]["id"] == str(no_inspection.id)


def test_sort_invalid_value(client: TestClient, make_user) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    res = client.get("/api/applications?sort=bogus", headers=auth_header(officer))
    assert res.status_code == 422


def test_default_sort_unchanged(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    make_application(status="SUBMITTED")
    res = client.get("/api/applications", headers=auth_header(officer))
    assert res.status_code == 200  # default created_desc still works, no sort= required


def test_list_query_count_does_not_grow_with_page_size(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    owner = make_user(Role.BUSINESS)
    for offset in range(5):
        app = make_application(owner, status="DOCUMENT_REVIEW", officer=officer)
        _schedule(client, officer, app.id, (clock.today() + timedelta(days=offset)).isoformat())

    counted: list[str] = []

    def on_execute(conn, cursor, statement, *a, **kw):  # noqa: ANN001, ANN201, ARG001
        if "FROM applications" in statement or "from applications" in statement.lower():
            counted.append(statement)

    event.listen(engine, "before_cursor_execute", on_execute)
    try:
        res = client.get(
            "/api/applications?sort=scheduled_asc&page_size=20", headers=auth_header(officer)
        )
    finally:
        event.remove(engine, "before_cursor_execute", on_execute)
    assert res.status_code == 200
    # One SELECT for items, one for the count subquery — not one per row.
    assert len(counted) <= 2, counted
