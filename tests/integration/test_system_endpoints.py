"""System endpoint + app-factory tests (M0 Slice 4).

Deterministic: no network, no wall-clock assertions, fresh app per test.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from argus.api.app import create_app
from argus.config import load_settings


def test_create_app_uses_injected_settings() -> None:
    settings = load_settings(_env_file=None, environment="staging", git_sha="abc123")
    app = create_app(settings)
    assert app.state.settings is settings


def test_health_is_liveness(app: FastAPI) -> None:
    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["content-type"].startswith("application/json")


def test_ready_is_ready_with_empty_registry(app: FastAPI) -> None:
    resp = TestClient(app).get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


def test_ready_reports_503_when_a_check_fails(app: FastAPI) -> None:
    app.state.readiness_checks = [("db", lambda: False), ("cache", lambda: True)]
    resp = TestClient(app).get("/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready", "failed": ["db"]}


def test_version_reflects_settings() -> None:
    settings = load_settings(_env_file=None, environment="staging", git_sha="deadbeef")
    resp = TestClient(create_app(settings)).get("/version")
    assert resp.json() == {
        "version": settings.version,
        "git_sha": "deadbeef",
        "environment": "staging",
    }


def test_openapi_title_and_version(app: FastAPI) -> None:
    schema = TestClient(app).get("/openapi.json").json()
    assert schema["info"]["title"] == "argus"
    assert schema["info"]["version"] == app.state.settings.version


def test_repeated_app_creation_does_not_duplicate_logging(
    capsys: pytest.CaptureFixture[str],
) -> None:
    import structlog

    for _ in range(3):
        create_app(load_settings(_env_file=None, environment="production"))
    capsys.readouterr()  # drop any construction noise
    structlog.get_logger().info("once")
    out = capsys.readouterr().out
    assert len([line for line in out.splitlines() if line]) == 1
