import pytest

from app.core.config import ConfigError, get_settings

SECRET = "super-secret-value-that-must-never-appear-0123456789"


@pytest.fixture
def fresh_settings(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_invalid_config_error_never_contains_values(fresh_settings) -> None:  # noqa: ANN001
    fresh_settings.setenv("JWT_SECRET", SECRET)
    fresh_settings.setenv("CRON_SECRET", SECRET)
    fresh_settings.setenv("STORAGE_BACKEND", "supabase")
    fresh_settings.setenv("SUPABASE_URL", "https://<project>.supabase.co")
    fresh_settings.setenv("SUPABASE_SERVICE_ROLE_KEY", "# backend only, NEVER expose")
    with pytest.raises(ConfigError) as exc_info:
        get_settings()
    message = str(exc_info.value)
    assert "SUPABASE_URL must be set" in message
    assert SECRET not in message and "postgresql" not in message
    assert exc_info.value.__cause__ is None and exc_info.value.__suppress_context__


def test_short_jwt_secret_is_reported_without_its_value(fresh_settings) -> None:  # noqa: ANN001
    fresh_settings.setenv("JWT_SECRET", "my short secret")
    with pytest.raises(ConfigError) as exc_info:
        get_settings()
    assert "JWT_SECRET" in str(exc_info.value)
    assert "my short secret" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("url", "key"),
    [
        ("https://rkgyzvzvpciapmfmkvvy.supabase.co", "# backend only, NEVER expose"),
        ("https://rkgyzvzvpciapmfmkvvy.supabase.co", ""),
        ("", "sb_secret_" + "a" * 32),
    ],
)
def test_storage_placeholders_rejected(fresh_settings, url: str, key: str) -> None:  # noqa: ANN001
    fresh_settings.setenv("STORAGE_BACKEND", "supabase")
    fresh_settings.setenv("SUPABASE_URL", url)
    fresh_settings.setenv("SUPABASE_SERVICE_ROLE_KEY", key)
    with pytest.raises(ConfigError):
        get_settings()


def test_real_looking_storage_config_accepted(fresh_settings) -> None:  # noqa: ANN001
    fresh_settings.setenv("STORAGE_BACKEND", "supabase")
    fresh_settings.setenv("SUPABASE_URL", "https://rkgyzvzvpciapmfmkvvy.supabase.co")
    fresh_settings.setenv("SUPABASE_SERVICE_ROLE_KEY", "sb_secret_" + "a" * 32)
    assert get_settings().STORAGE_BACKEND == "supabase"
