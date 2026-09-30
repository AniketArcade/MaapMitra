"""Spec 12: mocked, informational-only payments. POST /api/applications/{id}/mock-pay,
GET /api/applications/meta's payment_statuses, and the explicit "never gates a transition"
constraint."""

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Payment
from tests.conftest import auth_header
from tests.helpers import audit_rows


def _mock_pay(client: TestClient, user, application_id):  # noqa: ANN001, ANN201
    return client.post(f"/api/applications/{application_id}/mock-pay", headers=auth_header(user))


def _payment_row_count(application_id) -> int:  # noqa: ANN001
    with SessionLocal() as s:
        return s.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.application_id == application_id)
        )


# ---------------------------------------------------------------------------
# (a) owner can mock-pay; status becomes PAID with paid_at set
# ---------------------------------------------------------------------------


def test_mock_pay_success(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    app = make_application(owner)  # DRAFT: no gating on status, mock-pay works at any status

    res = _mock_pay(client, owner, app.id)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["payment"] == {
        "status": "PAID",
        "amount": None,
        "paid_at": body["payment"]["paid_at"],
    }
    assert body["payment"]["paid_at"] is not None

    audits = audit_rows("PAYMENT_MOCKED")
    assert len(audits) == 1
    assert audits[0].details == {"status": "PAID", "created": True}
    assert audits[0].entity_id == app.id
    assert _payment_row_count(app.id) == 1


def test_application_detail_payment_null_before_mock_pay(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    app = make_application(owner)
    detail = client.get(f"/api/applications/{app.id}", headers=auth_header(owner)).json()
    assert detail["payment"] is None


# ---------------------------------------------------------------------------
# (b) a non-owner BUSINESS gets 404 (org scoping)
# ---------------------------------------------------------------------------


def test_mock_pay_wrong_org_is_404(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    other_business = make_user(Role.BUSINESS)
    app = make_application(owner)

    res = _mock_pay(client, other_business, app.id)
    assert res.status_code == 404
    assert _payment_row_count(app.id) == 0


# ---------------------------------------------------------------------------
# (c) non-BUSINESS roles cannot call it
# ---------------------------------------------------------------------------


def test_mock_pay_non_business_roles_forbidden(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    app = make_application(owner, status="SUBMITTED")

    for role in (
        Role.LM_OFFICER,
        Role.GATC,
        Role.DISTRICT_ADMIN,
        Role.STATE_ADMIN,
        Role.SUPER_ADMIN,
    ):
        res = _mock_pay(client, make_user(role), app.id)
        assert res.status_code == 403, (role, res.text)
    assert _payment_row_count(app.id) == 0


# ---------------------------------------------------------------------------
# (d) calling mock-pay twice is idempotent/safe
# ---------------------------------------------------------------------------


def test_mock_pay_twice_is_idempotent(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    app = make_application(owner)

    first = _mock_pay(client, owner, app.id)
    assert first.status_code == 200
    paid_at_1 = first.json()["payment"]["paid_at"]

    second = _mock_pay(client, owner, app.id)
    assert second.status_code == 200
    body2 = second.json()
    assert body2["payment"]["status"] == "PAID"
    # Already-PAID is a no-op: paid_at is left exactly as first set, not bumped to "now" again.
    # Compared as datetimes, not raw strings: the second read round-trips through Postgres (whose
    # session timezone need not be UTC), so the same instant can print with a different offset.
    assert datetime.fromisoformat(body2["payment"]["paid_at"]) == datetime.fromisoformat(paid_at_1)

    # The unique application_id constraint (and the lock-then-lookup discipline in
    # services/payments.py: mock_pay()) means exactly one row ever exists, never two.
    assert _payment_row_count(app.id) == 1

    audits = audit_rows("PAYMENT_MOCKED")
    assert [a.details["created"] for a in audits] == [True, False]


# ---------------------------------------------------------------------------
# (e) applications/meta includes payment_statuses
# ---------------------------------------------------------------------------


def test_meta_includes_payment_statuses(client: TestClient, make_user) -> None:  # noqa: ANN001
    body = client.get("/api/applications/meta", headers=auth_header(make_user(Role.GATC))).json()
    assert body["payment_statuses"] == [
        {"value": "NOT_PAID", "label": "Not paid"},
        {"value": "PENDING", "label": "Payment pending"},
        {"value": "PAID", "label": "Paid"},
    ]


# ---------------------------------------------------------------------------
# (f) payment status never gates any existing transition: an application can reach
#     CERTIFICATE_ISSUED while payment stays untouched (null / not paid) throughout
# ---------------------------------------------------------------------------


def test_payment_never_gates_the_lifecycle(
    client: TestClient, make_user, make_application, storage
) -> None:  # noqa: ANN001
    officer = make_user(Role.LM_OFFICER)
    app = make_application(status="APPROVED", officer=officer)

    # mock-pay is never called for this application at any point in its lifecycle.
    detail = client.get(f"/api/applications/{app.id}", headers=auth_header(officer)).json()
    assert detail["status"] == "APPROVED"
    assert detail["payment"] is None  # no row: informational only, nothing ever required it

    res = client.post(f"/api/applications/{app.id}/certificate", headers=auth_header(officer))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "CERTIFICATE_ISSUED"
    assert body["certificate"] is not None
    # The explicit "informational only" constraint, proven in code: reaching the terminal
    # CERTIFICATE_ISSUED status never created, required, or even looked at a Payment row.
    assert body["payment"] is None
    assert _payment_row_count(app.id) == 0
