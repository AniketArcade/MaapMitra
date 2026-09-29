from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import Instrument, User
from app.seed import seed
from tests.conftest import auth_header


def test_seed_is_idempotent_and_demo_isolation_holds(client: TestClient, storage) -> None:  # noqa: ANN001
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

    # The seeded SUBMITTED application: in the officer's queue, invisible to ABC Traders
    assert any(c.startswith("application APP-") for c in first)
    queue = client.get("/api/applications?status=SUBMITTED", headers=auth_header(officer)).json()
    assert queue["total"] == 1
    app_id = queue["items"][0]["id"]
    detail = client.get(f"/api/applications/{app_id}", headers=auth_header(officer)).json()
    assert [d["content_type"] for d in detail["documents"]] == ["application/pdf", "image/png"]
    assert client.get(f"/api/applications/{app_id}", headers=auth_header(abc)).status_code == 404
    assert client.get("/api/applications", headers=auth_header(abc)).json()["total"] == 0
    assert len(storage.objects) == 2
