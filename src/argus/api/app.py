"""FastAPI application factory + lifespan (M0 spec §4.1).

API layer: may import framework/SDKs and inward (config, observability) (§1.1).

No import-time side effects: the app exists only once :func:`create_app` is
called, so tests build isolated instances and inject settings. There is no
hidden global mutable app state — settings and the (empty) readiness registry
live on ``app.state`` of each instance.
"""

import contextlib
from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI

from argus.api.errors import register_exception_handlers
from argus.api.middleware import CorrelationIdMiddleware
from argus.api.system import ReadinessCheck
from argus.api.system import router as system_router
from argus.config import Settings, load_settings
from argus.observability import configure_logging

_logger = structlog.get_logger()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure a FastAPI application.

    :param settings: injected for deterministic tests; falls back to
        :func:`load_settings` (env + optional ``.env``) which validates
        fail-fast, so a misconfigured process never produces an app.
    """
    settings = settings or load_settings()
    # Configure logging at construction so every app instance logs consistently
    # regardless of whether the ASGI lifespan runs (e.g. under TestClient).
    # configure_logging replaces structlog's global config, so repeated calls
    # do not duplicate output.
    configure_logging(settings)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _logger.info(
            "startup",
            service=settings.service_name,
            version=settings.version,
            environment=str(settings.environment),
        )
        yield
        _logger.info("shutdown", service=settings.service_name)

    app = FastAPI(
        title=settings.service_name,
        version=settings.version,
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Honest, empty readiness registry — the seam M1+ extends (§4.3).
    app.state.readiness_checks = list[ReadinessCheck]()

    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    app.include_router(system_router)
    return app
