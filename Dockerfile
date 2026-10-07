# ARGUS production image (M0 spec §9). Multi-stage, non-root, runtime-only deps.
#
# Stage 1 (builder): resolve + install EXACTLY what uv.lock pins into a venv.
# Stage 2 (runtime): copy only that venv onto a clean python:3.12-alpine. No uv,
# no build toolchain, no dev/test deps, no source tree, no package caches.
#
# Base is Alpine (musl), not Debian slim: the slim/trixie base ships OS packages
# (util-linux/ncurses/systemd/perl-base) carrying unfixed HIGH CVEs with no
# available fix, which the Slice 9 Trivy gate (HIGH/CRITICAL, no ignore-unfixed)
# blocks on. Alpine does not ship those packages -> 0 HIGH / 0 CRITICAL. Every
# current ARGUS dependency (incl. the pydantic-core Rust ext) ships musllinux
# wheels, so no compiler/build-base is needed here.
# REVISIT if ARGUS adds an in-process ML dep with no musllinux wheel (e.g. torch,
# onnxruntime): move to a glibc minimal base (e.g. Debian distroless) then.

# --- Stage 1: builder -------------------------------------------------------
FROM python:3.12-alpine AS builder

# Pinned uv binary (reproducible tooling). uv itself never ships in the runtime
# image — it exists only to perform the locked install here.
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /bin/uv

# UV_FROZEN: refuse to touch the lock; a stale uv.lock fails the build (§3.4).
# UV_PYTHON_DOWNLOADS=0: use the base image's interpreter, never a fetched one,
#   so the venv's python matches the runtime stage's python exactly.
# UV_COMPILE_BYTECODE=1: ship .pyc for faster, read-only cold starts.
# UV_LINK_MODE=copy: materialise files into the venv (no hardlinks to the cache,
#   which would dangle once the cache mount is gone).
ENV UV_FROZEN=1 \
    UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Layer 1 — dependencies only. Keyed on pyproject.toml + uv.lock so this layer
# is cached until the locked dependency set changes. --no-dev excludes the dev
# group (ruff/mypy/pytest/pytest-cov/httpx); --no-install-project defers the app
# itself so a source edit doesn't bust the dependency layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Layer 2 — the application. --no-editable installs argus as a real wheel into
# the venv's site-packages, so the runtime image needs no src/ tree on disk.
# README.md is required by pyproject (readme=) to build the package.
COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# --- Stage 2: runtime -------------------------------------------------------
FROM python:3.12-alpine AS runtime

# Minimal OCI metadata the build actually knows (§6). No invented version.
LABEL org.opencontainers.image.title="argus" \
      org.opencontainers.image.description="ARGUS FastAPI service (M0 production foundation)." \
      org.opencontainers.image.source="https://github.com/adivazana1256/ARGUS"

# Dedicated unprivileged user. No sudo, no shell login, no home clutter.
# BusyBox addgroup/adduser (Alpine) instead of Debian groupadd/useradd.
RUN addgroup -S argus \
    && adduser -S -G argus -H -s /sbin/nologin argus

# PYTHONUNBUFFERED: logs flush immediately (correct for container stdout).
# PATH: the copied venv's bin first so `uvicorn`/`python` resolve to it.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy only the fully-built venv (deps + argus wheel). Same path as the builder
# so the venv's absolute shebangs/symlinks stay valid. Owned by the app user.
COPY --from=builder --chown=argus:argus /app/.venv /app/.venv

# Build metadata (§14): GIT_SHA build arg -> ARGUS_GIT_SHA env, read by settings.
# Not a secret; defaults to "unknown" in local dev. Declared after the heavy
# COPY so changing the SHA doesn't rebuild the venv layer.
ARG GIT_SHA=unknown
ENV ARGUS_GIT_SHA=${GIT_SHA}

USER argus

EXPOSE 8000

# Liveness probe via the Python already in the image (no curl install, §5/§9.1).
# Bounded: 2s client timeout inside a 3s HEALTHCHECK timeout, 3 retries.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]

# Uvicorn is sufficient for the single M0 service (no Gunicorn, §9.1). Bind
# 0.0.0.0 so the port is reachable from outside the container.
CMD ["uvicorn", "argus.main:app", "--host", "0.0.0.0", "--port", "8000"]
