from sqlalchemy import func, select

from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models import AuditLog, RefreshToken, User


def audit_rows(action: str) -> list[AuditLog]:
    """Read in a fresh session, so we only see committed rows."""
    with SessionLocal() as s:
        return list(s.scalars(select(AuditLog).where(AuditLog.action == action)))


def active_refresh_tokens(user_id) -> int:  # noqa: ANN001
    with SessionLocal() as s:
        return s.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        )


def set_cookie_headers(response) -> list[str]:  # noqa: ANN001
    return response.headers.get_list("set-cookie")


def cleared(response, name: str) -> bool:  # noqa: ANN001
    return any(h.startswith(f"{name}=") and "Max-Age=0" in h for h in set_cookie_headers(response))


def submit_checklist(client, officer: User, inspection_id) -> None:  # noqa: ANN001
    """Drive an inspection's checklist to submitted via the API (spec 06's pattern): every
    checklist item PASS, every measurement observed at its expected value."""
    headers = {"Authorization": f"Bearer {create_access_token(officer)}"}
    detail = client.get(f"/api/inspections/{inspection_id}", headers=headers).json()
    res = client.patch(
        f"/api/inspections/{inspection_id}",
        json={
            "checklist_items": [
                {"item_key": i["item_key"], "result": "PASS"} for i in detail["checklist_items"]
            ],
            "measurements": [
                {"label": m["label"], "observed_value": str(m["expected_value"])}
                for m in detail["measurements"]
            ],
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    res = client.post(f"/api/inspections/{inspection_id}/submit", headers=headers)
    assert res.status_code == 200, res.text
