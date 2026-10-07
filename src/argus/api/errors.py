"""Stable JSON error envelope + exception handlers (M0 spec §4.4).

API layer: may import framework/SDKs and inward layers (§1.1).

One envelope for every handled error so clients get a predictable shape and a
``correlation_id`` to quote in a support request — without ever leaking internal
exception text or stack traces (`docs/SECURITY.md` §11, secure failure)::

    {"error": {"code", "message", "correlation_id", "details": [...]}}

``details`` is a list so it can carry structured, *non-sensitive* field errors
(e.g. validation locations) now and be extended later without changing the
envelope's top-level shape.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from argus.api.middleware import CORRELATION_HEADER, correlation_id_of


class ArgusError(Exception):
    """Base class for expected, client-facing application errors.

    Subclass or raise directly with an explicit, non-sensitive ``message``.
    The ``code`` is a stable machine-readable string; ``status_code`` maps to
    HTTP. Raising this (rather than a bare ``Exception``) is how handlers opt
    into the stable envelope instead of the generic 500.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "error",
        status_code: int = 400,
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or []


def _envelope(
    *, code: str, message: str, correlation_id: str, details: list[Any]
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
            "details": details,
        }
    }


def error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    details: list[Any] | None = None,
) -> JSONResponse:
    """Build the stable error envelope as a JSON response.

    The correlation id is read from request scope state (set by the middleware,
    survives contextvar teardown) and echoed in both the body and the response
    header so a client error can always be tied back to the server logs.
    """
    cid = correlation_id_of(request)
    return JSONResponse(
        status_code=status_code,
        content=_envelope(
            code=code, message=message, correlation_id=cid, details=details or []
        ),
        headers={CORRELATION_HEADER: cid},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the envelope onto expected errors and a generic 500 catch-all."""

    @app.exception_handler(ArgusError)
    async def _handle_argus_error(request: Request, exc: ArgusError) -> JSONResponse:
        return error_response(
            request,
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Expose only loc/msg/type — never the offending input value, which may
        # contain untrusted or sensitive data (`docs/SECURITY.md` §11).
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return error_response(
            request,
            code="validation_error",
            message="Request validation failed.",
            status_code=422,
            details=details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return error_response(
            request,
            code="http_error",
            message=str(exc.detail),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the real cause server-side (with traceback); return a generic
        # message so no internal detail reaches the client (secure failure).
        from structlog import get_logger

        get_logger().exception("unhandled_exception")
        return error_response(
            request,
            code="internal_error",
            message="An internal error occurred.",
            status_code=500,
        )
