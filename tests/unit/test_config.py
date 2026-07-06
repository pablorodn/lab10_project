import pytest
from pydantic import ValidationError

from app.config import SECRET_KEY_MIN_LENGTH, Settings

VALID_SECRET_KEY = "test-secret-key-for-test-suite-only"


def _settings(**overrides) -> Settings:
    base = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_ANON_KEY": "anon",
        "SUPABASE_SERVICE_ROLE_KEY": "service",
        "DATABASE_URL": "postgres://postgres:postgres@localhost:5432/postgres",
        "OPENROUTER_API_KEY": "test",
        "SECRET_KEY": VALID_SECRET_KEY,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


def test_is_production_false_by_default():
    assert _settings().is_production is False


def test_is_production_false_for_non_production_values():
    assert _settings(ENVIRONMENT="development").is_production is False
    assert _settings(ENVIRONMENT="staging").is_production is False


def test_is_production_true_only_for_production():
    assert _settings(ENVIRONMENT="production").is_production is True


def test_short_secret_key_fails_settings_construction():
    assert len(VALID_SECRET_KEY) >= SECRET_KEY_MIN_LENGTH
    with pytest.raises(ValidationError, match="SECRET_KEY must be at least"):
        _settings(SECRET_KEY="short-secret")


def test_secret_key_of_minimum_length_is_accepted():
    settings = _settings(SECRET_KEY="a" * SECRET_KEY_MIN_LENGTH)
    assert settings.secret_key == "a" * SECRET_KEY_MIN_LENGTH


def test_malformed_database_url_fails_settings_construction():
    with pytest.raises(ValidationError, match="DATABASE_URL must include a scheme and hostname"):
        _settings(DATABASE_URL="not-a-valid-url")


def test_database_url_missing_hostname_fails_settings_construction():
    with pytest.raises(ValidationError, match="DATABASE_URL must include a scheme and hostname"):
        _settings(DATABASE_URL="postgres://")


def test_valid_database_url_is_accepted():
    settings = _settings(DATABASE_URL="postgres://postgres:postgres@localhost:5432/postgres")
    assert settings.database_host == "localhost"


def test_file_tools_enabled_recognizes_lowercase_true():
    assert _settings(FILE_TOOLS_ENABLED="true").is_file_tools_enabled is True


def test_file_tools_enabled_recognizes_lowercase_false_without_warning(caplog):
    with caplog.at_level("WARNING", logger="app.config"):
        assert _settings(FILE_TOOLS_ENABLED="false").is_file_tools_enabled is False
    assert not any(
        r.message.__contains__("FILE_TOOLS_ENABLED") for r in caplog.records
    )


def test_file_tools_enabled_unset_resolves_false_without_warning(caplog):
    with caplog.at_level("WARNING", logger="app.config"):
        assert _settings().is_file_tools_enabled is False
    assert not caplog.records


@pytest.mark.parametrize("raw_value", ["1", "True"])
def test_file_tools_enabled_ambiguous_value_warns_and_resolves_false(raw_value, caplog):
    with caplog.at_level("WARNING", logger="app.config"):
        result = _settings(FILE_TOOLS_ENABLED=raw_value).is_file_tools_enabled
    assert result is False
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warning_records
    assert any(
        getattr(r, "raw_value", None) == raw_value for r in warning_records
    )
