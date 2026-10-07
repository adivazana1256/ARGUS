"""Correlation-ID + request-logging ASGI middleware (M0 spec §4.5, §6).

API layer: may import framework/SDKs and inward layers (§1.1).

Why a pure-ASGI middleware (not ``BaseHTTPMiddleware``): it runs in the *same*
context as the endpoint, so the ``correlation_id`` bound into
``structlog.contextvars`` here is visible to every log line in the request and
is reliably cleared in ``finally`` — no cross-request context leakage.

Canonical header contract (chosen + documented):
    ``X-Request-ID`` — single header for both directions.
    - Inbound: accepted *only* if it is well-formed (see ``_SAFE_ID``); any
      malformed/oversized/absent value is ignored and a fresh UUIDv4 is
      generated instead. Incoming header data is untrusted, so it is validated
      before it is ever bound, logged, or echoed (log-injection defense).
    - Outbound: always echoed so a client can correlate with server logs.
"""

import re
import time
from typing import Any

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from argus.observability import bind_correlation_id, clear_correlation_id

CORRELATION_HEADER = "X-Request-ID"
_STATE_KEY = "correlation_id"

# Accept a conservative, log-safe id: visible ASCII id chars, bounded length.
# Rejects CR/LF (header/log injection), spaces, and oversized values.
_SAFE_ID = re.compile(r"\A[A-Za-z0-9._-]{1,128}\Z")

_logger = structlog.get_logger()


def _accept_incoming(raw: str | None) -> str | None:
    """Return the inbound id only if it is well-formed, else ``None``."""
    return raw if raw is not None and _SAFE_ID.match(raw) else None


def correlation_id_of(request: Request) -> str:
    """Read the request's correlation id from scope state (set below).

    Survives contextvar teardown, so exception handlers can still quote it.
    """
    value = request.scope.get("state", {}).get(_STATE_KEY)
    return value if isinstance(value, str) else "unknown"


class CorrelationIdMiddleware:
    """Bind a request-scoped correlation id and log request completion."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(CORRELATION_HEADER)
        correlation_id = bind_correlation_id(_accept_incoming(incoming))
        # Stash on scope state so exception handlers (which run after contextvar
        # teardown) can still read it. Starlette surfaces this as request.state.
        scope.setdefault("state", {})[_STATE_KEY] = correlation_id

        status_code = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[CORRELATION_HEADER] = correlation_id
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # Let the exception propagate to the registered 500 handler, but
            # record the failure here with safe fields only.
            self._log(scope, 500, start, correlation_id, failed=True)
            raise
        else:
            self._log(scope, status_code, start, correlation_id)
        finally:
            clear_correlation_id()

    @staticmethod
    def _log(
        scope: Scope,
        status_code: int,
        start: float,
        correlation_id: str,
        *,
        failed: bool = False,
    ) -> None:
        # Safe fields only: method, path, status, duration, correlation_id.
        # Deliberately NOT logged: query string, request body, auth/cookie or
        # arbitrary headers (`docs/SECURITY.md` §10, §12).
        fields: dict[str, Any] = {
            "method": scope.get("method"),
            "path": scope.get("path"),
            "status_code": status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            "correlation_id": correlation_id,
        }
        if failed:
            _logger.error("request_failed", **fields)
        else:
            _logger.info("request_completed", **fields)
