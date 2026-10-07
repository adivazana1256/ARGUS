# ARGUS

ARGUS is a production-oriented **Agentic Cyber Threat Investigation Platform**.
The system is designed to receive a security event or Indicator of Compromise
(IOC), gather evidence from trusted security tools and knowledge sources, reason
over that evidence, investigate gaps, and produce an **evidence-backed** verdict.

It is built around one core principle:

> **The LLM is not the source of truth. Evidence is.**

LLMs are used for planning, orchestration, correlation, reasoning and report
generation. Security tools, structured data and retrieved knowledge provide the
factual foundation. See [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md).

---

## Project status

**Milestone 0 — Production Engineering Foundation: complete.**

M0 delivers a runnable, tested, secure, observable FastAPI service skeleton with
its quality gates, CI/CD, container packaging and supply-chain hygiene — **and
nothing from the security/AI domain yet**. It is the scaffold, not the house.

The investigation core, agent orchestration, RAG, MCP tool integration and
evaluation harness are **upcoming milestones — planned, not implemented**. See
[Roadmap](#roadmap) and [Current limitations](#current-limitations--non-goals).

What exists **today** (M0):

- A FastAPI service with `/health`, `/ready`, `/version` endpoints.
- Typed, fail-fast configuration (`pydantic-settings`).
- Structured JSON logging with request-scoped correlation IDs (`structlog`).
- A structured error envelope with a catch-all that never leaks internals.
- Enforced architectural layer boundaries (import-boundary tests).
- Full local quality gate + CI (lint, format, strict types, tests, coverage).
- Supply-chain scanning: Gitleaks, pip-audit, Trivy, CodeQL, Dependabot.
- A hardened, non-root, multi-stage production container image.

---

## Architecture

ARGUS uses a `src/` layout with explicit layers and an enforced inward-only
dependency rule (see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)):

```
api ───────────┐
application ───┼──> domain
infrastructure ┘
config, observability   = cross-cutting (import none of the above)
```

- **`domain/`** — pure business types/rules; stdlib + pydantic only. *(empty in M0)*
- **`application/`** — use-cases + ports (interfaces). *(empty in M0)*
- **`infrastructure/`** — adapters: DB, external APIs, model providers. *(empty in M0)*
- **`api/`** — FastAPI delivery layer only: factory, system endpoints, error
  model, correlation-ID middleware.
- **`config/`, `observability/`** — cross-cutting settings and logging.

The rule is **enforced by tests**, not convention:
`tests/architecture/test_import_boundaries.py` walks the AST of `src/argus/**`
and fails the build if an inner layer imports an outer one, or if any module
imports from `spikes/`.

### Endpoints

System endpoints are mounted at the app **root** (unversioned — liveness/readiness
probes must not be tied to an API version). Versioned business routes (`/api/v1`)
will arrive with the investigation core.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness: process is up. Always `200 {"status":"ok"}`, no dependency checks. |
| GET | `/ready` | Readiness: `200` when able to serve. Pluggable check registry (empty in M0 ⇒ ready); `503` with failing names otherwise. |
| GET | `/version` | Non-sensitive build metadata: `{version, git_sha, environment}`. |

### Correlation IDs (`X-Request-ID`)

Every request gets a correlation ID bound into the logging context and echoed on
the response. The middleware reads an inbound `X-Request-ID` **only if it is
well-formed** (bounded ASCII; CR/LF and oversized values rejected as a
log-injection defense) and otherwise generates a UUIDv4. The ID appears on every
log line of the request and in handled error envelopes.

---

## Technology stack

| Concern | Choice |
|---------|--------|
| Language / runtime | Python, pinned `>=3.12,<3.13` |
| Web framework | FastAPI + Starlette |
| ASGI server | Uvicorn |
| Validation / settings | Pydantic v2 / pydantic-settings |
| Logging | structlog (JSON in non-dev, console in dev) |
| Packaging / deps | uv + committed `uv.lock` (`--frozen` installs) |
| Build backend | hatchling |
| Lint + format | Ruff (lint + formatter) |
| Type checking | mypy (strict) |
| Tests | pytest + pytest-cov + httpx |
| Container | Multi-stage Docker, `python:3.12-alpine`, non-root |

Runtime dependencies are deliberately minimal (`fastapi`, `uvicorn`, `pydantic`,
`pydantic-settings`, `structlog`). All lint/type/test tooling lives in a single
`dev` dependency group and **never ships in the image**. LangGraph, model-provider
SDKs, databases and MCP libraries are intentionally **not** dependencies yet.

---

## Local setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen        # install locked deps (fails on a stale uv.lock)
make hooks-install      # optional: install the pre-commit hook
```

`make sync` is the same locked install wrapped in the Makefile.

### Running locally

```bash
uv run uvicorn argus.main:app --reload
# then:
curl localhost:8000/health
curl localhost:8000/ready
curl localhost:8000/version
```

Configuration is environment-based with the `ARGUS_` prefix (e.g.
`ARGUS_ENVIRONMENT`, `ARGUS_LOG_LEVEL`); an optional local `.env` (git-ignored)
is supported for dev. See [`.env.example`](.env.example). Invalid config
fails fast at startup with a non-secret message.

---

## Command surface

Everything is a thin wrapper over uv / the selected tooling (`make help` lists all):

| Command | Does |
|---------|------|
| `make sync` | `uv sync --frozen` — locked install; fails on a stale lock. |
| `make lint` | `ruff check`. |
| `make format` | `ruff format` (modifies files). |
| `make format-check` | `ruff format --check` (no modification). |
| `make typecheck` | strict `mypy` over `src` and `tests`. |
| `make test` | `pytest` with the coverage gate. |
| `make check` | `sync` + `lint` + `format-check` + `typecheck` + `test` — the full local gate, mirrors CI. |
| `make docker-build` | Build the production image. |
| `make audit` | `pip-audit` the locked environment (needs network). |
| `make security` | `gitleaks detect` + `pip-audit` (requires gitleaks installed). |

---

## Testing

- `pytest` with `pytest-cov`; FastAPI `TestClient` (httpx) for API tests.
- Tests are split into `tests/unit/`, `tests/integration/`, and
  `tests/architecture/` (layering / import-boundary enforcement).
- **Coverage gate: 85% line coverage on `src/argus`, enforced in CI**
  (`--cov-fail-under=85`); the current suite runs well above it.
- Deterministic by rule: no network, no wall-clock reliance, no paid API calls.

```bash
make test        # or: make check for the full gate
```

---

## Docker (production image)

The image is multi-stage and security-first (see [`Dockerfile`](Dockerfile)):

- **Builder stage** installs exactly what `uv.lock` pins into a venv (runtime
  deps only, `--no-dev`), using a pinned `uv` binary that never ships in the
  final image.
- **Runtime stage** copies only that venv onto a clean base — no uv, no build
  toolchain, no dev/test deps, no source tree, no caches.
- **Non-root**: runs as an unprivileged `argus` user.
- **Base**: `python:3.12-alpine`. The Debian `slim` base shipped OS packages
  (util-linux, ncurses, systemd, perl-base) carrying **unfixed** HIGH CVEs with
  no available fix; Alpine does not ship them, bringing the image scan to **0
  HIGH / 0 CRITICAL** and roughly halving image size (~228 MB → ~114 MB). The
  current locked ARGUS dependency set builds and runs successfully on Alpine
  without adding a compiler or build toolchain. See the glibc/musl revisit
  condition documented in the `Dockerfile` header.
- **Healthcheck** probes `/health` using the Python already in the image (no
  `curl` installed).

```bash
make docker-build IMAGE=argus:dev
docker run --rm -p 8000:8000 argus:dev
```

---

## CI/CD and security gates

Three GitHub Actions workflows, each with least-privilege (`contents: read`)
tokens and third-party Actions pinned to commit SHAs:

- **[`ci.yml`](.github/workflows/ci.yml)** — quality gates (lint, format,
  strict mypy, tests + coverage) and the production Docker build.
- **[`security.yml`](.github/workflows/security.yml)** — supply-chain scanning,
  one authority per layer:
  - **Gitleaks** — committed secrets (full history).
  - **pip-audit** — Python dependency CVEs (PyPA/OSV advisory DB).
  - **Trivy** — built container image CVEs (OS/base-image + system libraries),
    `HIGH,CRITICAL`, no `ignore-unfixed`, no suppression; HIGH/CRITICAL is
    blocking.
- **[`codeql.yml`](.github/workflows/codeql.yml)** — SAST over ARGUS's own code.
- **[`.github/dependabot.yml`](.github/dependabot.yml)** — dependency + GitHub
  Actions update PRs.

### Security posture

- Secrets never committed (`.env` git-ignored, `.env.example` placeholders only;
  Gitleaks in pre-commit **and** CI) and never logged (secret-typed fields use
  `SecretStr`; request logging records only safe fields).
- Secure failure: handled errors return a generic envelope with a correlation
  ID — no stack traces or internals leak.
- Pinned, reproducible dependencies (`uv.lock`, `--frozen`).

Details: [`docs/SECURITY.md`](docs/SECURITY.md).

---

## Documentation

- [`docs/PRODUCT_SPEC.md`](docs/PRODUCT_SPEC.md) — product vision and scope.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture and layering.
- [`docs/SECURITY.md`](docs/SECURITY.md) — security model and controls.
- [`docs/EVALUATION.md`](docs/EVALUATION.md) — evaluation principles.
- [`docs/ENGINEERING_LOOP.md`](docs/ENGINEERING_LOOP.md) — how work is built and reviewed.
- [`docs/milestones/M0_PRODUCTION_FOUNDATION.md`](docs/milestones/M0_PRODUCTION_FOUNDATION.md) — the M0 specification and delivery status.
- Architecture Decision Records:
  - [ADR-001 — PostgreSQL + pgvector](docs/adr/001-postgresql-pgvector.md) *(accepted; not yet implemented)*
  - [ADR-002 — Agent orchestration framework](docs/adr/002-agent-orchestration-framework.md) *(accepted; not yet implemented)*

### Orchestration decision

**LangGraph has been selected** as ARGUS's agent orchestration framework
(ADR-002). **Production agent orchestration is not implemented yet** — LangGraph
is deliberately kept out of the production dependencies and behind an interface
until the investigation-core milestone. A frozen, isolated spike under
`spikes/orchestration/` informed the decision and is reference-only (never
imported by production code).

---

## Roadmap

M0 (foundation) is complete. Upcoming milestones, **planned and not yet
implemented**, build on it in reviewable slices:

- **Investigation core** — deterministic evidence model and verdict logic in
  `domain/` + `application/`.
- **Persistence** — PostgreSQL + pgvector (ADR-001).
- **Agent orchestration** — LangGraph behind an interface (ADR-002).
- **Retrieval-Augmented Generation (RAG)** over security knowledge.
- **MCP-based secure tool integration** and threat-intelligence sources.
- **Evaluation harness** and AI guardrails.

---

## Current limitations / non-goals

As of M0, ARGUS **does not** yet perform threat investigations, and has **no**
agentic workflows, RAG, MCP tools, model-provider calls, database, authn/authz,
frontend, or cloud/Kubernetes deployment. These are explicit M0 non-goals (see
[`docs/milestones/M0_PRODUCTION_FOUNDATION.md`](docs/milestones/M0_PRODUCTION_FOUNDATION.md) §16)
and belong to later milestones. The repository today is a production-grade
*foundation* — treat any capability not listed under "What exists today" as
planned.

---

## Repository structure

```
ARGUS/
├── src/argus/            # production package (src layout)
│   ├── api/              # FastAPI delivery layer
│   ├── application/      # use-cases + ports (empty in M0)
│   ├── domain/           # business types/rules (empty in M0)
│   ├── infrastructure/   # adapters (empty in M0)
│   ├── config/           # typed settings
│   ├── observability/    # structured logging
│   └── main.py           # ASGI entrypoint (app = create_app())
├── tests/                # unit / integration / architecture
├── spikes/               # frozen, isolated experiments — not production
├── docs/                 # product, architecture, security, ADRs, milestones
├── Dockerfile            # multi-stage, non-root production image
├── Makefile              # developer command surface
├── pyproject.toml        # single source of truth for deps + tool config
└── uv.lock               # pinned, reproducible dependency lock
```

---

## Development workflow

Changes land as small, independently reviewable slices, each gated by
`make check` locally and the full CI/security suite on the PR. Install the
pre-commit hook (`make hooks-install`) to run the fast hooks (Ruff + Gitleaks +
file hygiene) on every commit; strict mypy and the full test suite run in
`make check` and CI. See [`docs/ENGINEERING_LOOP.md`](docs/ENGINEERING_LOOP.md).
