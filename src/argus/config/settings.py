"""Typed application settings (M0 spec §5, §14).

Cross-cutting: this module imports only stdlib + pydantic (§1.1). It must never
import from domain/application/api/infrastructure/spikes.

Design notes:
- Values come from real environment variables and an optional local ``.env``
  (dev only; ``.env`` is git-ignored). Real environment variables override
  ``.env`` — this is pydantic-settings' default source precedence.
- Construction is fail-fast: an invalid ``ARGUS_ENVIRONMENT`` / ``ARGUS_LOG_LEVEL``
  (or any unknown ``ARGUS_*`` key) raises ``ValidationError`` with a non-secret
  message, so a misconfigured process never boots.
- No global mutable settings state. Build a fresh instance via
  ``load_settings()``; tests override by passing kwargs (including ``_env_file``).
- Secrets: future secret fields use ``pydantic.SecretStr`` so their values are
  redacted in ``repr``/``str``/``model_dump`` used in ordinary diagnostics. M0
  has no secrets yet (§5), so none are declared here; the type is the mechanism.
"""

from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment. Any other value fails validation."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Log level, mirroring stdlib ``logging`` names."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def _resolve_version() -> str:
    """Resolve the installed package version (single source: ``__init__``)."""
    try:
        return version("argus")
    except PackageNotFoundError:  # pragma: no cover - only if run uninstalled
        return "0.0.0+unknown"


class Settings(BaseSettings):
    """M0-level application configuration.

    Only configuration that genuinely exists at M0 lives here. No speculative
    DB/Redis/model-provider/LangGraph/RAG/MCP/cloud settings (§3.3, §16).
    """

    model_config = SettingsConfigDict(
        env_prefix="ARGUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    environment: Environment = Environment.LOCAL
    log_level: LogLevel = LogLevel.INFO
    service_name: str = "argus"
    # Build metadata (§14). version is resolved from the package; git_sha is
    # injected at container build via ARGUS_GIT_SHA, "unknown" in local dev.
    version: str = _resolve_version()
    git_sha: str = "unknown"

    @field_validator("environment", mode="before")
    @classmethod
    def _lower_environment(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


def load_settings(**overrides: Any) -> Settings:
    """Construct and validate a fresh ``Settings`` instance.

    Explicit factory (no cached global) so callers and tests get isolated,
    overridable instances. ``overrides`` are forwarded to the model, including
    pydantic-settings control kwargs such as ``_env_file``.
    """
    return Settings(**overrides)
