"""Deterministic tests for typed settings (M0 Slice 2).

No network, no real credentials, no reliance on the developer's environment:
every test either clears ``ARGUS_*`` and disables ``.env`` (``_env_file=None``)
or points at a temp ``.env``. Secret redaction is exercised with synthetic,
test-only data.
"""

import os
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from argus.config import Environment, LogLevel, load_settings


@pytest.fixture(autouse=True)
def _clear_argus_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip any ARGUS_* vars so tests are isolated from the dev environment."""
    for key in [k for k in os.environ if k.startswith("ARGUS_")]:
        monkeypatch.delenv(key, raising=False)


def test_defaults() -> None:
    settings = load_settings(_env_file=None)
    assert settings.environment is Environment.LOCAL
    assert settings.log_level is LogLevel.INFO
    assert settings.service_name == "argus"
    assert settings.git_sha == "unknown"
    assert settings.version  # resolved from the installed package


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_ENVIRONMENT", "production")
    monkeypatch.setenv("ARGUS_SERVICE_NAME", "argus-api")
    settings = load_settings(_env_file=None)
    assert settings.environment is Environment.PRODUCTION
    assert settings.service_name == "argus-api"


def test_log_level_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_LOG_LEVEL", "info")
    assert load_settings(_env_file=None).log_level is LogLevel.INFO


def test_environment_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_ENVIRONMENT", "PRODUCTION")
    assert load_settings(_env_file=None).environment is Environment.PRODUCTION


def test_invalid_environment_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_ENVIRONMENT", "dev")
    with pytest.raises(ValidationError):
        load_settings(_env_file=None)


def test_invalid_log_level_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARGUS_LOG_LEVEL", "verbose")
    with pytest.raises(ValidationError):
        load_settings(_env_file=None)


def test_dotenv_loaded(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ARGUS_ENVIRONMENT=staging\n")
    assert load_settings(_env_file=str(env_file)).environment is Environment.STAGING


def test_real_env_overrides_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ARGUS_ENVIRONMENT=staging\n")
    monkeypatch.setenv("ARGUS_ENVIRONMENT", "production")
    settings = load_settings(_env_file=str(env_file))
    assert settings.environment is Environment.PRODUCTION


class _SecretSettings(BaseSettings):
    """Test-only model proving the SecretStr redaction mechanism (§5)."""

    model_config = SettingsConfigDict(env_prefix="ARGUS_TEST_")

    token: SecretStr = SecretStr("")


def test_secret_redaction() -> None:
    fake = "swordfish-synthetic-value"  # noqa: S105 - test-only, not a real secret
    settings = _SecretSettings(token=SecretStr(fake))

    assert fake not in repr(settings)
    assert fake not in str(settings)
    assert fake not in str(settings.model_dump())
    assert fake not in str(settings.model_dump(mode="json"))
    # The value is still retrievable deliberately, only never leaked by default.
    assert settings.token.get_secret_value() == fake


def test_settings_dump_has_no_secret_value_leak() -> None:
    # The field set is pinned so a new field can't slip in unreviewed; a new
    # *secret* field must be a SecretStr (asserted below).
    dumped = load_settings(_env_file=None).model_dump()
    assert set(dumped) == {
        "environment",
        "log_level",
        "service_name",
        "version",
        "git_sha",
        "anthropic_api_key",
        "llm_model",
        "llm_timeout_seconds",
        "llm_max_retries",
    }


def test_llm_defaults() -> None:
    settings = load_settings(_env_file=None)
    assert settings.anthropic_api_key is None  # no key needed unless the real adapter
    assert settings.llm_model == "claude-opus-4-8"
    assert settings.llm_timeout_seconds == 30.0
    assert settings.llm_max_retries == 2


def test_anthropic_api_key_is_redacted_everywhere() -> None:
    from pydantic import SecretStr

    settings = load_settings(_env_file=None, anthropic_api_key="sk-super-secret")
    # Env-sourced secret is a SecretStr: its value never appears in repr/str or
    # model_dump() used in ordinary diagnostics.
    assert isinstance(settings.anthropic_api_key, SecretStr)
    assert "sk-super-secret" not in repr(settings)
    assert "sk-super-secret" not in str(settings.model_dump())
    assert settings.anthropic_api_key.get_secret_value() == "sk-super-secret"
