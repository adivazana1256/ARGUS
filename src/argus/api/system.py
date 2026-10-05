"""Operational endpoints: liveness, readiness, version (M0 spec §4.2, §4.3).

Mounted at the app root (unversioned): liveness/readiness probes must not be
tied to an API version. Handlers are thin — no business logic (§4.6).

Readiness is honest: M0 has no external dependencies, so the check registry is
empty and the service reports ready. The registry (``app.state.readiness_checks``)
is the documented seam where M1+ registers real checks (DB, etc.) *without*
changing this endpoint's contract — it is not a faked DB/Redis/model check.
"""

from collections.abc import Callable

from fastapi import APIRouter, Request, Response, status

from argus.config import Settings

# A readiness check: name -> predicate returning True when healthy.
ReadinessCheck = tuple[str, Callable[[], bool]]

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up and the event loop responds. No deps."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, object]:
    """Readiness: can the service serve traffic now?

    Runs every registered check; 503 with the failing names if any fail.
    Empty registry (M0) => ready.
    """
    checks: list[ReadinessCheck] = getattr(request.app.state, "readiness_checks", [])
    failed = [name for name, check in checks if not check()]
    if failed:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "failed": failed}
    return {"status": "ready"}


@router.get("/version")
async def version(request: Request) -> dict[str, str]:
    """Non-sensitive build metadata (§14)."""
    settings: Settings = request.app.state.settings
    return {
        "version": settings.version,
        "git_sha": settings.git_sha,
        "environment": str(settings.environment),
    }
