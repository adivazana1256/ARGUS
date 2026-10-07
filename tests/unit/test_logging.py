"""Deterministic tests for the structured logging baseline (M0 Slice 3).

No network, no wall-clock assertions, no reliance on the developer's
environment. Each test configures logging explicitly against an in-memory
``StringIO`` stream and inspects the rendered output.
"""

import contextvars
import io
import json
from typing import Any

import pytest
import structlog
from pydantic import SecretStr

from argus.config import load_settings
from argus.observability import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
)


@pytest.fixture(autouse=True)
def _reset_structlog() -> Any:
    """Keep structlog's global config/context from leaking between tests."""
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()


def _configure(stream: io.StringIO, **overrides: Any) -> Any:
    settings = load_settings(_env_file=None, **overrides)
    configure_logging(settings, stream=stream)
    return structlog.get_logger()


def _lines(stream: io.StringIO) -> list[str]:
    return [line for line in stream.getvalue().splitlines() if line]


def test_production_renders_json() -> None:
    buf = io.StringIO()
    log = _configure(buf, environment="production")
    log.info("hello")
    (line,) = _lines(buf)
    record = json.loads(line)  # fails loudly if not valid JSON
    assert record["event"] == "hello"


def test_staging_renders_json() -> None:
    buf = io.StringIO()
    log = _configure(buf, environment="staging")
    log.warning("careful")
    (line,) = _lines(buf)
    record = json.loads(line)
    assert record["event"] == "careful"
    assert record["log_level"] == "warning"


@pytest.mark.parametrize("environment", ["local", "test"])
def test_dev_environments_render_console_not_json(environment: str) -> None:
    buf = io.StringIO()
    log = _configure(buf, environment=environment)
    log.info("dev_event")
    (line,) = _lines(buf)
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)
    assert "dev_event" in line


def test_log_level_filtering() -> None:
    buf = io.StringIO()
    log = _configure(buf, environment="production", log_level="WARNING")
    log.debug("suppressed")
    log.info("suppressed")
    log.warning("emitted")
    log.error("emitted")
    records = [json.loads(line) for line in _lines(buf)]
    events = [r["event"] for r in records]
    assert events == ["emitted", "emitted"]
    assert all(r["log_level"] in {"warning", "error"} for r in records)


def test_required_common_metadata_present() -> None:
    buf = io.StringIO()
    log = _configure(buf, environment="production", git_sha="deadbeef")
    log.info("with_meta")
    record = json.loads(_lines(buf)[0])
    assert set(record) >= {
        "event",
        "log_level",
        "timestamp",
        "service",
        "environment",
        "version",
        "git_sha",
    }
    assert record["service"] == "argus"
    assert record["environment"] == "production"
    assert record["git_sha"] == "deadbeef"


def test_git_sha_omitted_when_unknown() -> None:
    buf = io.StringIO()
    log = _configure(buf, environment="production")  # git_sha defaults to "unknown"
    log.info("no_sha")
    record = json.loads(_lines(buf)[0])
    assert "git_sha" not in record


def test_correlation_id_binding() -> None:
    buf = io.StringIO()
    log = _configure(buf, environment="production")
    returned = bind_correlation_id("fixed-corr-id")
    log.info("bound")
    record = json.loads(_lines(buf)[0])
    assert returned == "fixed-corr-id"
    assert record["correlation_id"] == "fixed-corr-id"


def test_correlation_id_generated_when_absent() -> None:
    buf = io.StringIO()
    log = _configure(buf, environment="production")
    cid = bind_correlation_id()
    log.info("auto")
    record = json.loads(_lines(buf)[0])
    assert cid and record["correlation_id"] == cid


def test_correlation_id_clearing() -> None:
    buf = io.StringIO()
    log = _configure(buf, environment="production")
    bind_correlation_id("to-be-cleared")
    clear_correlation_id()
    log.info("after_clear")
    record = json.loads(_lines(buf)[0])
    assert "correlation_id" not in record


def test_context_isolation_between_contexts() -> None:
    buf = io.StringIO()
    log = _configure(buf, environment="production")
    bind_correlation_id("outer")

    def _in_isolated_context() -> None:
        # A copied context must not see the outer binding, and its own binding
        # must not leak back out.
        clear_correlation_id()
        bind_correlation_id("inner")
        log.info("inner_line")

    contextvars.copy_context().run(_in_isolated_context)
    log.info("outer_line")

    records = [json.loads(line) for line in _lines(buf)]
    by_event = {r["event"]: r for r in records}
    assert by_event["inner_line"]["correlation_id"] == "inner"
    assert by_event["outer_line"]["correlation_id"] == "outer"


def test_repeated_configuration_does_not_duplicate_output() -> None:
    buf = io.StringIO()
    settings = load_settings(_env_file=None, environment="production")
    configure_logging(settings, stream=buf)
    configure_logging(settings, stream=buf)
    configure_logging(settings, stream=buf)
    structlog.get_logger().info("once")
    assert len(_lines(buf)) == 1


def test_secretstr_value_is_not_exposed() -> None:
    buf = io.StringIO()
    log = _configure(buf, environment="production")
    secret = "swordfish-synthetic-value"  # noqa: S105 - test-only, not real
    log.info("leaky", token=SecretStr(secret))
    output = buf.getvalue()
    assert secret not in output
    # The field is still present, just masked.
    record = json.loads(_lines(buf)[0])
    assert "token" in record
