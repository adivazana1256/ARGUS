"""Structured logging baseline (M0 spec §6), OTel-ready.

Cross-cutting: this module may import only stdlib, ``structlog`` and
``argus.config`` (§1.1). It must never import domain/application/api/
infrastructure/spikes.

Design:
- Logging is configured **explicitly** via :func:`configure_logging`. Importing
  this module has no side effects (no handlers, no global config) — call the
  function from the application/test entrypoint.
- Rendering is environment-aware: ``local``/``test`` get the human-readable
  ``ConsoleRenderer``; ``staging``/``production`` get machine-readable JSON.
  The JSON schema (§ "common fields" below) is the stable baseline later layers
  build on; the console output is a developer convenience and is not a contract.
- Correlation context uses ``structlog.contextvars`` (ultimately stdlib
  ``contextvars``), so a ``correlation_id`` bound in one async context does not
  leak into another. This is the seam the future FastAPI request middleware
  (Slice 4) binds into — no middleware is implemented here.

Common fields emitted on every structured (JSON) event:
    event, log_level, timestamp, service, environment, version,
    and git_sha when available (i.e. not the local-dev "unknown" sentinel).

No speculative investigation/agent/tool fields are added globally; those are
per-event responsibilities of later layers.

Secret hygiene: this module never serializes the ``Settings`` object, and no
helper here dumps settings/credentials. ``pydantic.SecretStr`` values mask
themselves under ``repr``/``str`` (which is how both renderers serialize unknown
types), so a ``SecretStr`` passed as a field value is not exposed. It cannot and
does not promise to redact arbitrary plaintext strings a caller chooses to log —
callers are responsible for passing secrets as ``SecretStr`` or not at all.
"""

import logging
from typing import Any, TextIO
from uuid import uuid4

import structlog
from structlog.contextvars import (
    bind_contextvars,
    merge_contextvars,
    unbind_contextvars,
)
from structlog.typing import EventDict, WrappedLogger

from argus.config import Environment, Settings

_CORRELATION_ID_KEY = "correlation_id"
_JSON_ENVIRONMENTS = frozenset({Environment.STAGING, Environment.PRODUCTION})


def _common_fields_processor(settings: Settings) -> Any:
    """Build a processor that stamps the stable common fields onto every event.

    ``git_sha`` is only included when genuinely available (§5/§14: the local-dev
    sentinel ``"unknown"`` is omitted rather than logged as a field).
    """
    base: dict[str, str] = {
        "service": settings.service_name,
        "environment": str(settings.environment),
        "version": settings.version,
    }
    if settings.git_sha and settings.git_sha != "unknown":
        base["git_sha"] = settings.git_sha

    def processor(
        logger: WrappedLogger, method_name: str, event_dict: EventDict
    ) -> EventDict:
        for key, value in base.items():
            event_dict.setdefault(key, value)
        return event_dict

    return processor


def _rename_level_to_log_level(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Rename structlog's ``level`` key to the project-standard ``log_level``."""
    if "level" in event_dict:
        event_dict["log_level"] = event_dict.pop("level")
    return event_dict


def configure_logging(settings: Settings, *, stream: TextIO | None = None) -> None:
    """Configure structlog explicitly from typed settings.

    Idempotent: ``structlog.configure`` *replaces* the global configuration
    rather than appending, and we attach no stdlib handlers, so calling this
    more than once (e.g. tests + app startup) never duplicates output.

    :param stream: optional output stream (used by tests to capture rendered
        output). Defaults to structlog's standard print-to-stdout factory.
    """
    use_json = settings.environment in _JSON_ENVIRONMENTS

    shared: list[Any] = [
        merge_contextvars,
        structlog.processors.add_log_level,
    ]
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp")

    if use_json:
        processors = [
            *shared,
            _rename_level_to_log_level,
            timestamper,
            _common_fields_processor(settings),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            *shared,
            timestamper,
            _common_fields_processor(settings),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(),
        ]

    level = logging.getLevelNamesMapping()[str(settings.log_level)]

    logger_factory: Any = (
        structlog.WriteLoggerFactory(file=stream)
        if stream is not None
        else structlog.PrintLoggerFactory()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=logger_factory,
        # Keep caching disabled so explicit reconfiguration remains reliable
        # across tests and startup; revisit only if profiling shows a need.
        cache_logger_on_first_use=False,
    )


def bind_correlation_id(correlation_id: str | None = None) -> str:
    """Bind a ``correlation_id`` into the current (context-local) log context.

    Generates a UUIDv4 when none is supplied. Safe for async FastAPI request
    handling: binding happens in ``contextvars``, so concurrent requests do not
    share or overwrite each other's id. Returns the bound id.
    """
    cid = correlation_id or str(uuid4())
    bind_contextvars(**{_CORRELATION_ID_KEY: cid})
    return cid


def clear_correlation_id() -> None:
    """Unbind the ``correlation_id`` from the current log context.

    Only the correlation id is removed; other context-local bindings are left
    intact. Call this at request teardown (future middleware).
    """
    unbind_contextvars(_CORRELATION_ID_KEY)
