from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import Instrument, User
from app.seed import seed
from tests.conftest import auth_header


def test_seed_is_idempotent_and_demo_isolation_holds(client: TestClient) -> None:
    with SessionLocal() as s:
        first = seed(s, "LmDemo@2026")
        second = seed(s, "LmDemo@2026")
        assert any(c.startswith("instrument OTH-0001") for c in first)
        assert second == []
        assert s.scalar(select(func.count()).select_from(User)) == 6
        abc = s.scalar(select(User).where(User.email == "owner@abctraders.demo"))
        officer = s.scalar(select(User).where(User.email == "officer.dhn@lm.demo"))
        oth = s.scalar(select(Instrument).where(Instrument.serial_number == "OTH-0001"))
    assert client.get("/api/instruments", headers=auth_header(abc)).json()["total"] == 0
    assert client.get(f"/api/instruments/{oth.id}", headers=auth_header(abc)).status_code == 404
    assert client.get(f"/api/instruments/{oth.id}", headers=auth_header(officer)).status_code == 200
