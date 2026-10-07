"""Error-envelope tests (M0 Slice 4): stable shape, no internal leakage."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from argus.api.errors import ArgusError
from argus.api.middleware import CORRELATION_HEADER


def _envelope_ok(body: dict[str, object]) -> None:
    assert set(body) == {"error"}
    err = body["error"]
    assert isinstance(err, dict)
    assert set(err) >= {"code", "message", "correlation_id", "details"}


def test_404_uses_stable_envelope(app: FastAPI) -> None:
    resp = TestClient(app).get("/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    _envelope_ok(body)
    assert body["error"]["code"] == "http_error"
    assert body["error"]["correlation_id"] == resp.headers[CORRELATION_HEADER]


def test_expected_argus_error_maps_to_envelope(app: FastAPI) -> None:
    @app.get("/boom-expected")
    async def _boom() -> None:
        raise ArgusError("teapot", code="im_a_teapot", status_code=418)

    resp = TestClient(app).get("/boom-expected")
    assert resp.status_code == 418
    body = resp.json()
    _envelope_ok(body)
    assert body["error"]["code"] == "im_a_teapot"
    assert body["error"]["message"] == "teapot"


def test_unexpected_exception_returns_generic_500_no_leak(app: FastAPI) -> None:
    secret_detail = "ORA-00942: table SECRET_USERS does not exist"  # noqa: S105

    @app.get("/boom-unexpected")
    async def _boom() -> None:
        raise RuntimeError(secret_detail)

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/boom-unexpected")
    assert resp.status_code == 500
    body = resp.json()
    _envelope_ok(body)
    assert body["error"]["code"] == "internal_error"
    # No internal detail / stack trace leaks to the client.
    assert secret_detail not in resp.text
    assert "Traceback" not in resp.text
    assert body["error"]["correlation_id"] == resp.headers[CORRELATION_HEADER]


def test_validation_error_hides_input_value(app: FastAPI) -> None:
    @app.get("/needs-int")
    async def _needs_int(n: int) -> dict[str, int]:
        return {"n": n}

    resp = TestClient(app).get("/needs-int?n=not-a-number")
    assert resp.status_code == 422
    body = resp.json()
    _envelope_ok(body)
    assert body["error"]["code"] == "validation_error"
    # loc/msg/type kept; the offending input value is not echoed back.
    assert "not-a-number" not in resp.text
