import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.config import get_settings
from app.core.deps import get_client_ip
from app.core.roles import Role
from tests.conftest import BASE_URL, PASSWORD, auth_header, register_body
from tests.helpers import audit_rows


def test_each_security_event_writes_one_row(client: TestClient, make_user) -> None:  # noqa: ANN001
    client.post("/api/auth/register", json=register_body())
    client.post("/api/auth/login", json={"email": "owner@abc.demo", "password": PASSWORD})
    client.post("/api/auth/login", json={"email": "owner@abc.demo", "password": "WrongPass1"})
    client.post("/api/auth/logout")  # the client's cookie jar holds the latest refresh cookie
    admin = make_user(Role.SUPER_ADMIN)
    TestClient(client.app, base_url=BASE_URL).post(
        "/api/users",
        json={
            "email": "o@lm.demo",
            "full_name": "O",
            "role": "LM_OFFICER",
            "password": PASSWORD,
            "state_code": "JH",
            "district_code": "DHN",
        },
        headers=auth_header(admin),
    )
    for action in ("USER_REGISTERED", "LOGIN_SUCCEEDED", "LOGIN_FAILED", "LOGOUT", "USER_CREATED"):
        rows = audit_rows(action)
        assert len(rows) == 1, action
        assert rows[0].ip_address == "testclient", action


def _request(headers: dict[str, str], peer: str = "10.0.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234)})


@pytest.mark.parametrize(
    ("hops", "xff", "expected"),
    [
        (0, "1.1.1.1", "10.0.0.1"),  # untrusted header ignored
        (1, "1.1.1.1", "1.1.1.1"),
        (1, "6.6.6.6, 1.1.1.1", "1.1.1.1"),  # spoofed leftmost entry ignored
        (2, "6.6.6.6, 1.1.1.1, 2.2.2.2", "1.1.1.1"),
        (2, "1.1.1.1", "10.0.0.1"),  # fewer entries than hops: fall back to peer
    ],
)
def test_get_client_ip(monkeypatch: pytest.MonkeyPatch, hops: int, xff: str, expected: str) -> None:
    monkeypatch.setattr(get_settings(), "TRUSTED_PROXY_HOPS", hops)
    assert get_client_ip(_request({"X-Forwarded-For": xff})) == expected
