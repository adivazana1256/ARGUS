"""Correlation-id lifecycle + request-logging security (M0 Slice 4).

Deterministic: fixed/known ids, no wall-clock assertions.
"""

import json
import uuid

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from argus.api.middleware import CORRELATION_HEADER


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def test_generated_id_when_absent(app: FastAPI) -> None:
    resp = TestClient(app).get("/health")
    cid = resp.headers[CORRELATION_HEADER]
    assert _is_uuid(cid)


def test_valid_incoming_id_is_honored(app: FastAPI) -> None:
    sent = "req-abc_123.OK"
    resp = TestClient(app).get("/health", headers={CORRELATION_HEADER: sent})
    assert resp.headers[CORRELATION_HEADER] == sent


def test_oversized_incoming_id_is_replaced(app: FastAPI) -> None:
    resp = TestClient(app).get("/health", headers={CORRELATION_HEADER: "x" * 500})
    cid = resp.headers[CORRELATION_HEADER]
    assert cid != "x" * 500
    assert _is_uuid(cid)


def test_injection_incoming_id_is_replaced(app: FastAPI) -> None:
    # CR/LF and spaces must be rejected (header/log injection defense).
    resp = TestClient(app).get("/health", headers={CORRELATION_HEADER: "bad id"})
    assert _is_uuid(resp.headers[CORRELATION_HEADER])


def test_no_context_leakage_between_requests(app: FastAPI) -> None:
    client = TestClient(app)
    first = client.get("/health", headers={CORRELATION_HEADER: "first-id"})
    second = client.get("/health")
    assert first.headers[CORRELATION_HEADER] == "first-id"
    # Second request did not inherit the first id, and context is cleared.
    assert second.headers[CORRELATION_HEADER] != "first-id"
    assert structlog.contextvars.get_contextvars().get("correlation_id") is None


def test_request_logging_omits_query_and_sensitive_headers(
    app: FastAPI, capsys: pytest.CaptureFixture[str]
) -> None:
    client = TestClient(app)
    capsys.readouterr()
    client.get(
        "/health?token=supersecretvalue",
        headers={
            "Authorization": "Bearer leakme-abc",
            "Cookie": "session=leakme-cookie",
        },
    )
    out = capsys.readouterr().out
    completion = [
        json.loads(line)
        for line in out.splitlines()
        if line and json.loads(line).get("event") == "request_completed"
    ]
    assert completion, "expected a request_completed log line"
    record = completion[-1]
    blob = json.dumps(record)
    assert "supersecretvalue" not in blob
    assert "leakme-abc" not in blob
    assert "leakme-cookie" not in blob
    assert set(record) >= {
        "method",
        "path",
        "status_code",
        "duration_ms",
        "correlation_id",
    }
    assert record["path"] == "/health"  # no query string
