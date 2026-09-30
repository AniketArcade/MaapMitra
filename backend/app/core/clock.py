"""The current instant and date, factored out so tests can freeze time.

Tests monkeypatch `now_utc`, not `datetime.now` directly:
    monkeypatch.setattr("app.core.clock.now_utc", lambda: datetime(2026, 10, 14, 20, 0, tzinfo=UTC))
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def now_utc() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    """Today's date in APP_TIMEZONE — the authority for scheduling validation."""
    tz = ZoneInfo(get_settings().APP_TIMEZONE)
    return now_utc().astimezone(tz).date()
