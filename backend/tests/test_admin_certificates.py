"""Spec 10: GET /api/admin/certificates/stats and .../expiring-soon — ADMIN_ROLES only,
jurisdiction-scoped the same way scope_applications/scope_certificates already are."""

from datetime import timedelta

from fastapi.testclient import TestClient

from app.core import clock
from app.core.roles import Role
from app.db.session import SessionLocal
from app.models import Certificate
from app.models.certificate import CertificateStatus
from tests.conftest import auth_header


def _issue(client: TestClient, officer, application_id) -> dict:  # noqa: ANN001
    res = client.post(
        f"/api/applications/{application_id}/certificate", headers=auth_header(officer)
    )
    assert res.status_code == 200, res.text
    return res.json()["certificate"]


def _set(certificate_id: str, **fields) -> None:  # noqa: ANN001
    with SessionLocal() as s:
        row = s.get(Certificate, certificate_id)
        assert row is not None
        for k, v in fields.items():
            setattr(row, k, v)
        s.commit()


def test_admin_certificates_roles_forbidden(client: TestClient, make_user) -> None:  # noqa: ANN001
    for role in (Role.BUSINESS, Role.LM_OFFICER, Role.GATC):
        headers = auth_header(make_user(role))
        assert client.get("/api/admin/certificates/stats", headers=headers).status_code == 403
        assert (
            client.get("/api/admin/certificates/expiring-soon", headers=headers).status_code == 403
        )


def test_admin_certificates_scope(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    dhn_officer = make_user(Role.LM_OFFICER)  # JH/DHN (defaults)
    rnc_officer = make_user(Role.LM_OFFICER, district_code="RNC")

    dhn_owner = make_user(Role.BUSINESS)  # org defaults to JH/DHN
    rnc_owner = make_user(Role.BUSINESS, org_district="RNC")

    dhn_app = make_application(dhn_owner, status="APPROVED", officer=dhn_officer)
    rnc_app = make_application(rnc_owner, status="APPROVED", officer=rnc_officer)
    dhn_cert = _issue(client, dhn_officer, dhn_app.id)
    rnc_cert = _issue(client, rnc_officer, rnc_app.id)

    super_admin = make_user(Role.SUPER_ADMIN)
    state_admin = make_user(Role.STATE_ADMIN)  # JH
    district_admin = make_user(Role.DISTRICT_ADMIN)  # JH/DHN

    def numbers(user) -> set[str]:  # noqa: ANN001
        res = client.get("/api/admin/certificates/expiring-soon", headers=auth_header(user))
        assert res.status_code == 200, res.text
        return {c["certificate_number"] for c in res.json()["items"]}

    # Neither certificate is "expiring soon" yet (2-year validity) -- move both into the window.
    _set(dhn_cert["id"], valid_until=clock.today() + timedelta(days=10))
    _set(rnc_cert["id"], valid_until=clock.today() + timedelta(days=10))

    all_numbers = {dhn_cert["certificate_number"], rnc_cert["certificate_number"]}
    assert numbers(super_admin) == all_numbers
    assert numbers(state_admin) == all_numbers  # both orgs are in JH
    assert numbers(district_admin) == {dhn_cert["certificate_number"]}  # DHN only


def test_admin_certificates_stats_zero_filled_and_inclusive(
    client: TestClient, make_user, make_application
) -> None:  # noqa: ANN001
    admin = make_user(Role.SUPER_ADMIN)
    officer = make_user(Role.LM_OFFICER)

    empty = client.get("/api/admin/certificates/stats", headers=auth_header(admin)).json()
    assert empty == {"valid": 0, "expiring_soon": 0, "expired": 0, "revoked": 0}

    far_out = _issue(client, officer, make_application(status="APPROVED", officer=officer).id)
    soon = _issue(client, officer, make_application(status="APPROVED", officer=officer).id)
    expired = _issue(client, officer, make_application(status="APPROVED", officer=officer).id)
    revoked = _issue(client, officer, make_application(status="APPROVED", officer=officer).id)

    _set(soon["id"], valid_until=clock.today() + timedelta(days=5))
    _set(
        expired["id"],
        valid_until=clock.today() - timedelta(days=1),
        status=CertificateStatus.EXPIRED,
    )
    _set(
        revoked["id"],
        valid_until=clock.today() - timedelta(days=1),
        status=CertificateStatus.REVOKED,
    )

    stats = client.get("/api/admin/certificates/stats", headers=auth_header(admin)).json()
    # valid is inclusive of expiring_soon (far_out + soon), not a disjoint bucket.
    assert stats == {"valid": 2, "expiring_soon": 1, "expired": 1, "revoked": 1}
    assert far_out["certificate_number"]  # sanity: far_out was actually created
