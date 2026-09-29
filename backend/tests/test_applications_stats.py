"""GET /applications/stats: shape, scoping consistency, RBAC and route order."""

import pytest
from fastapi.testclient import TestClient

from app.core.application_types import ApplicationStatus
from app.core.roles import Role
from tests.conftest import auth_header

ALL_STATUSES = [s.value for s in ApplicationStatus]


def _stats(client: TestClient, user) -> dict:  # noqa: ANN001
    res = client.get("/api/applications/stats", headers=auth_header(user))
    assert res.status_code == 200, res.text
    return res.json()


def test_shape(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    make_application(owner, status="SUBMITTED")
    body = _stats(client, owner)
    assert set(body["by_status"]) == set(ALL_STATUSES)
    assert body["by_status"]["SUBMITTED"] == 1
    assert all(v == 0 for k, v in body["by_status"].items() if k != "SUBMITTED")
    assert body["total"] == 1


def test_org_isolation(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    a, b = make_user(Role.BUSINESS), make_user(Role.BUSINESS)
    make_application(a, status="DRAFT")
    make_application(b, status="SUBMITTED")
    make_application(b, status="DOCUMENT_REVIEW")
    make_application(b, status="REJECTED")

    stats_a = _stats(client, a)
    assert stats_a["total"] == 1 and stats_a["by_status"]["DRAFT"] == 1

    stats_b = _stats(client, b)
    assert stats_b["total"] == 3
    assert (
        stats_b["by_status"]["SUBMITTED"],
        stats_b["by_status"]["DOCUMENT_REVIEW"],
        stats_b["by_status"]["REJECTED"],
    ) == (1, 1, 1)
    assert stats_b["by_status"]["DRAFT"] == 0


def test_officials_scoped_and_exclude_drafts(
    client: TestClient,
    make_user,
    make_instrument,
    make_application,  # noqa: ANN001
) -> None:
    owner = make_user(Role.BUSINESS)
    dhn_draft = make_instrument(owner, state_code="JH", district_code="DHN")
    dhn_submitted = make_instrument(owner, state_code="JH", district_code="DHN")
    rnc = make_instrument(owner, state_code="JH", district_code="RNC")
    pat = make_instrument(owner, state_code="BR", district_code="PAT")
    make_application(owner, dhn_draft, status="DRAFT")
    make_application(owner, dhn_submitted, status="SUBMITTED")
    make_application(owner, rnc, status="SUBMITTED")
    make_application(owner, pat, status="SUBMITTED")

    dhn_officer = _stats(client, make_user(Role.LM_OFFICER))  # JH / DHN
    assert dhn_officer["total"] == 1 and dhn_officer["by_status"]["SUBMITTED"] == 1
    assert dhn_officer["by_status"]["DRAFT"] == 0  # officials never count DRAFT

    jh_state_admin = _stats(client, make_user(Role.STATE_ADMIN))
    assert jh_state_admin["total"] == 2  # DHN + RNC, not PAT (BR)

    super_admin = _stats(client, make_user(Role.SUPER_ADMIN))
    assert super_admin["total"] == 3  # all non-DRAFT across states


@pytest.mark.parametrize("status", ["DRAFT", "SUBMITTED", "DOCUMENT_REVIEW", "REJECTED"])
def test_consistent_with_list_totals(
    client: TestClient, make_user, make_application, status: str
) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    make_application(owner, status=status)
    stats = _stats(client, owner)
    listed = client.get(f"/api/applications?status={status}", headers=auth_header(owner)).json()
    assert stats["by_status"][status] == listed["total"]
    assert stats["total"] == sum(stats["by_status"].values())


ALL_ROLES = list(Role)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_rbac(client: TestClient, make_user, role: Role) -> None:  # noqa: ANN001
    res = client.get("/api/applications/stats", headers=auth_header(make_user(role)))
    assert res.status_code == (403 if role == Role.GATC else 200)


def test_anonymous(client: TestClient) -> None:
    assert client.get("/api/applications/stats").status_code == 401


def test_route_order_not_swallowed_by_id(client: TestClient, make_user) -> None:  # noqa: ANN001
    # /applications/{id} expects a UUID; if /stats were declared after it, this would
    # 422 on UUID parsing instead of returning stats.
    res = client.get("/api/applications/stats", headers=auth_header(make_user(Role.BUSINESS)))
    assert res.status_code == 200
    assert set(res.json()) == {"total", "by_status"}


def test_volume_past_one_page(client: TestClient, make_user, make_application) -> None:  # noqa: ANN001
    owner = make_user(Role.BUSINESS)
    count = 105
    for _ in range(count):
        make_application(owner, status="DRAFT")
    stats = _stats(client, owner)
    assert stats["total"] == count
    assert stats["by_status"]["DRAFT"] == count
    listed = client.get("/api/applications?status=DRAFT", headers=auth_header(owner)).json()
    assert listed["total"] == count
