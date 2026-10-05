# ARGUS — Milestone 0: Production Engineering Foundation

- Status: APPROVED (architecture review complete; not yet implemented)
- Date: 2026-10-05
- Branch: `feat/m0-production-foundation`
- Type: Implementation specification. No production code is implemented by this
  document. The core engineering decisions below are human-approved (§18);
  implementation proceeds as small reviewable slices (§17).

---

## 0. Purpose and Scope

M0 creates the production-grade engineering foundation on which the
deterministic cyber investigation core (M1+) and the later LangGraph/RAG layers
can safely be built.

M0 delivers a runnable, testable, secure, observable FastAPI service skeleton
with its quality gates, CI, container packaging and supply-chain hygiene — and
**nothing from the security/AI domain yet**. It is the scaffold, not the house.

This specification is binding on implementation. It is intentionally detailed so
that the foundation can be built as a sequence of small reviewable slices
(§17), each independently verifiable, rather than as one uncontrolled
AI-generated change. This aligns with `docs/ENGINEERING_LOOP.md` §2 and §17.

### 0.1 Governing principles (from existing docs)

- Evidence over assumptions. Decisions in this doc cite the spike
  (`spikes/orchestration/RESULTS.md`) or existing ADRs where relevant.
- Security boundaries must be deterministic application code
  (`docs/SECURITY.md` §2). M0 builds the *place* those boundaries will live.
- The production core stays framework-independent where possible
  (`docs/ARCHITECTURE.md` §17): AI frameworks and external APIs belong behind
  interfaces. M0 therefore does **not** pull LangGraph into production.
- Minimal dependencies. No speculative infrastructure. Testability and
  inspectability are first-class.
- Spike code is reference, not source. Nothing is copied from
  `spikes/orchestration/` into production without explicit per-item
  justification and review.

---

## 1. Production Repository Structure

M0 establishes a `src/`-layout package with explicit architectural layers.
`src/` layout is chosen so tests run against the installed package (not the
working directory), which catches packaging mistakes early.

```
ARGUS/
├── src/
│   └── argus/
│       ├── __init__.py            # __version__ (single source, see §14)
│       ├── main.py                # ASGI entrypoint: app = create_app()
│       ├── domain/                # pure business types/rules; NO framework imports
│       │   └── __init__.py
│       ├── application/           # use-cases + ports (interfaces); orchestrates domain
│       │   └── __init__.py
│       ├── infrastructure/        # adapters: DB, external APIs, model providers (stubs only in M0)
│       │   └── __init__.py
│       ├── api/                   # FastAPI delivery layer ONLY
│       │   ├── __init__.py
│       │   ├── app.py             # application factory + lifespan
│       │   ├── errors.py          # structured error model + exception handlers
│       │   ├── middleware.py      # correlation/request ID middleware
│       │   └── v1/
│       │       ├── __init__.py
│       │       ├── router.py      # aggregates v1 routes
│       │       └── system.py      # /health, /ready, /version handlers (thin)
│       ├── config/                # typed settings (cross-cutting)
│       │   ├── __init__.py
│       │   └── settings.py
│       └── observability/         # logging (cross-cutting; OTel-ready)
│           ├── __init__.py
│           └── logging.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── architecture/              # import-boundary / layering tests (§7)
├── spikes/                        # EXISTING — frozen, isolated, not production
├── docs/
├── pyproject.toml                 # source of truth (§3)
├── uv.lock                        # pinned, reproducible (§3, §12)
├── .env.example                   # placeholders only, no secrets (§5)
├── Dockerfile                     # multi-stage, non-root (§9)
├── .dockerignore
├── Makefile                       # command surface (§13)
├── .pre-commit-config.yaml        # (§8)
└── .github/
    ├── workflows/
    │   ├── ci.yml                 # (§10)
    │   └── codeql.yml             # (§10, §11)
    └── dependabot.yml             # (§11, §12)
```

### 1.1 Layer dependency rule (enforced by tests, §7)

Allowed import direction (inner never imports outer):

```
api  ─────────┐
application ──┼──> domain
infrastructure┘
config, observability  = cross-cutting, importable by any layer, import none of the above
```

- `domain/` imports only stdlib + pydantic. No FastAPI, no SQLAlchemy, no httpx.
- `application/` imports `domain` + defines ports (Protocols/ABCs). No web/DB SDKs.
- `infrastructure/` and `api/` may import inward; they are the only layers
  allowed framework/SDK imports.
- **No production module may import from `spikes/`.** Enforced by test
  `tests/architecture/test_import_boundaries.py` (§7.4).

### 1.2 Spike isolation

`spikes/` remains exactly as-is: its own `pyproject.toml`, its own `.venv`, its
own Python (3.14.5). It is explicitly excluded from the production package, from
coverage, from the production lock file, and from the Docker build context
(`.dockerignore`). The production package never adds `spikes/` to `sys.path`.

---

## 2. Python / Runtime Decision

**Decision (approved): Python 3.12 (pinned `>=3.12,<3.13`) for production.**

### Rationale (evidence-based)

- The spike ran on **Python 3.14.5 and surfaced dependency deprecation
  warnings** (`spikes/orchestration/RESULTS.md` §7: `openai-agents` emits an
  `asyncio.get_event_loop_policy` DeprecationWarning; LangGraph checkpoint
  serialization warnings). 3.14 is bleeding-edge and parts of the intended
  production ecosystem (SQLAlchemy, pgvector drivers, model/agent SDKs, OTel
  exporters) are not yet warning-clean or wheel-complete on it.
- We optimize for ecosystem stability and compatibility, not newest-version
  vanity. 3.12 has: universal wheel availability across the planned stack
  (FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, psycopg, OTel), multiple years
  of upstream security support remaining, and performance already well ahead of
  3.10/3.11.
- 3.13 is viable but still younger in the data/AI dependency ecosystem; 3.11
  is older than necessary. 3.12 is the current "safe default" sweet spot.
- Pinning `<3.13` is deliberate: it prevents an accidental interpreter bump from
  silently changing behavior. Raising the ceiling is a reviewed decision, not a
  drift.

This is a **reversible, low-lock-in** choice. The exact minor (3.12) is
human-approved (§18); raising the ceiling later remains a reviewed decision.

---

## 3. Dependency / Package Management

### 3.1 Source of truth

`pyproject.toml` is the single source of truth for metadata and dependencies.
No `requirements.txt`, no `setup.py`.

### 3.2 Tooling: `uv`

**Decision (approved): `uv` for environment + lock + install, with a committed
`uv.lock`.**

- Fast, single static binary, deterministic resolver, produces a cross-platform
  `uv.lock` committed to the repo (reproducibility, §12).
- Native `pyproject.toml` support and dependency groups.
- CI and Docker install from the lock with `uv sync --frozen` (fails if lock is
  stale — reproducibility is enforced, not hoped for).

`uv` introduces a tool dependency and a lock-file format; this trade-off was
reviewed and approved (§18). It is **not** a production runtime dependency — it
never ships in the image layer that runs the app.

### 3.3 Dependency groups (separation)

```toml
[project]
dependencies = [            # runtime — minimal
  "fastapi",
  "uvicorn[standard]",
  "pydantic",
  "pydantic-settings",
  "structlog",
]

[dependency-groups]
dev = [                     # local + CI quality tooling
  "ruff",
  "mypy",
  "pre-commit",
  "pip-audit",
]
test = [                    # test execution
  "pytest",
  "pytest-cov",
  "httpx",                  # required by FastAPI TestClient
]
```

Rationale for each **runtime** dependency (minimal-dependency discipline):

| Dep | Why it is in M0 | Why not deferred |
|-----|-----------------|------------------|
| `fastapi` | Delivery layer required by M0. | Core of the milestone. |
| `uvicorn[standard]` | ASGI server to actually run/healthcheck. | Needed to start the app. |
| `pydantic` | Typed models, already the project's validation standard (`docs/ARCHITECTURE.md` §14). | Foundational. |
| `pydantic-settings` | Typed, fail-fast env config (§5). | Avoids hand-rolled env parsing. |
| `structlog` | Structured JSON logs + contextvar-bound correlation IDs (§6), clean OTel migration path. | Hand-rolling a JSON formatter + contextvar plumbing is more code to maintain than one small, stable dep. Approved in §18. |

Explicitly **not** added in M0: LangGraph, OpenAI/Anthropic SDKs, SQLAlchemy,
Alembic, psycopg, pgvector, redis, celery, any MCP library. Orchestration and
data layers belong to later milestones (`docs/ARCHITECTURE.md` §5, §12; ADR-002
consequences). Adding them now would be speculative infrastructure.

### 3.4 Lock / reproducibility strategy

- `uv.lock` is committed and is the authority for exact versions + hashes.
- `uv sync --frozen` in CI and Docker — a drifted lock fails the build.
- Direct runtime dependencies are declared with conservative lower bounds in
  `pyproject.toml`; exact pins live in `uv.lock` (so Dependabot/renovate can
  propose lock bumps without rewriting `pyproject.toml`).

---

## 4. FastAPI Foundation

### 4.1 Application factory + lifecycle

- `create_app() -> FastAPI` in `api/app.py`. No module-level side effects; the
  app is built by a factory so tests construct isolated instances.
- `main.py` exposes `app = create_app()` for `uvicorn argus.main:app`.
- Lifecycle via the ASGI **lifespan** context manager (not deprecated
  `@app.on_event`). M0 lifespan is near-empty (load/validate settings, bind
  logging context, log startup banner with version/env). It is the documented
  seam where DB pools/clients attach in later milestones.

### 4.2 Versioned API structure

- All routes mounted under `/api/v1` via `api/v1/router.py`.
- System endpoints (`/health`, `/ready`, `/version`) are mounted at the app root
  (unversioned) because liveness/readiness probes should not be tied to an API
  version. Documented explicitly.

### 4.3 Health / readiness endpoints

- `GET /health` — **liveness**: process is up. Always `200 {"status":"ok"}` if
  the event loop responds. No dependency checks.
- `GET /ready` — **readiness**: returns `200` when the app can serve traffic.
  In M0 there are no external deps, so it returns ready; it is built as a
  pluggable check registry (list of `name -> callable`) so M1+ can register DB
  connectivity without changing the endpoint contract. Returns `503` with the
  failing check names when any check fails.
- Separation of liveness vs readiness is deliberate (Kubernetes-ready later
  without committing to K8s now — `docs/ARCHITECTURE.md` §21).

### 4.4 Structured error model

- One JSON error envelope for all handled errors:

  ```json
  {
    "error": {
      "code": "validation_error",
      "message": "human-readable, non-sensitive",
      "correlation_id": "…",
      "details": []
    }
  }
  ```

- Exception handlers in `api/errors.py` for: `RequestValidationError` (422),
  a base `ArgusError` domain exception hierarchy (mapped to status codes), and a
  catch-all `500` that logs the exception with correlation ID and returns a
  **generic** message (no stack traces, no internals leaked — `docs/SECURITY.md`
  §11, secure failure).
- `correlation_id` is always included so a user-facing error can be tied to a
  server log line without exposing internals.

### 4.5 Request / correlation IDs

- Middleware in `api/middleware.py`: read inbound `X-Request-ID` (or
  `X-Correlation-ID`) if present and well-formed; otherwise generate a UUIDv4.
- Bind it into a `contextvar` consumed by structlog so every log line in the
  request carries it (§6), and echo it back in the response header.
- This is the foundation for the correlation/trace IDs required across
  `docs/ARCHITECTURE.md` §19 and the audit requirements in `docs/SECURITY.md`
  §12.

### 4.6 No business logic in route handlers

- Route handlers only: parse/validate input (Pydantic), call an
  application-layer callable, map the result to a response model. No domain
  logic, no I/O orchestration in handlers. Enforced by review and by the thin
  shape of `api/v1/*` (system endpoints call tiny functions, not inline logic).

---

## 5. Configuration and Secrets

- Typed settings via `pydantic-settings` `BaseSettings` in `config/settings.py`,
  prefixed `ARGUS_` (e.g. `ARGUS_ENVIRONMENT`, `ARGUS_LOG_LEVEL`).
- Environment-based: values come from environment variables and an optional
  local `.env` (dev only; `.env` is git-ignored — `docs/SECURITY.md` §10).
- **Fail-fast validation**: settings are constructed and validated at startup
  (in lifespan). Invalid/missing required config aborts boot with a clear,
  **non-secret** message. A mistyped `ARGUS_ENVIRONMENT` must not start.
- `.env.example` is committed with **placeholders only** — no real secrets, per
  `docs/SECURITY.md` §10. M0 has essentially no secrets yet (no DB, no API keys);
  the file documents the shape and is the pattern future secrets follow.
- **No secrets committed or logged**: secret-typed settings use Pydantic
  `SecretStr`; logging config (§6) never serializes the settings object wholesale
  and redacts known secret fields. Secret scanning (§11) enforces the "never
  committed" half in CI and pre-commit.
- `settings` is provided to the app via a cached accessor (dependency-injectable)
  so tests can override it without touching the environment.

---

## 6. Logging and Observability Baseline

Scope for M0 is a **logging baseline that is OTel-ready**, not a full
observability stack. Deploying Prometheus/Grafana/collectors now would be
speculative infrastructure (`docs/ARCHITECTURE.md` §19 lists them as *planned*;
§21 says infra is introduced only when there is a real requirement).

- Structured logs via `structlog`, JSON renderer in non-dev, console renderer in
  dev (controlled by settings).
- Every log event carries, by default: `service` (`argus`), `version` (§14),
  `environment`, `timestamp`, `level`, and `correlation_id` when inside a request
  (bound via contextvar from §4.5).
- stdlib `logging` is routed through structlog so uvicorn/third-party logs share
  the same format.
- **OTel-ready, not OTel-now**: the logging module centralizes context binding so
  that adding an OpenTelemetry exporter later (traces/metrics) is an additive
  change — correlation IDs already map cleanly onto trace/span IDs. No OTel
  dependency is added in M0.
- No secret values are logged (§5).

---

## 7. Testing

- **pytest** as the runner. `pytest-cov` for coverage. `httpx` for FastAPI
  `TestClient` API tests.
- Directory separation with markers:
  - `tests/unit/` — pure, fast, no network, no sleep, deterministic (settings,
    logging binding, error mapping, version resolution).
  - `tests/integration/` — FastAPI app via `TestClient` (health, ready, version,
    error envelope, correlation-ID echo, 404/422 shapes).
  - `tests/architecture/` — layering/import-boundary tests (§7.4).
- **Deterministic tests**: no reliance on wall-clock, randomness without a fixed
  seed, network, or ordering. Enforced via `pytest` config and review.
- **No external paid APIs in automated tests** (`docs/EVALUATION.md` principle;
  the spike proved 0-paid-call suites are achievable). M0 has no model calls at
  all; this is trivially satisfied and encoded as a standing rule.

### 7.4 Architecture / import-boundary tests

A zero-dependency test walks the AST of `src/argus/**` and asserts:

1. No production module imports anything under `spikes.*` or from the `spikes/`
   path. **(Hard requirement — acceptance criterion §15.)**
2. `domain/` imports only stdlib + `pydantic` (no `fastapi`, no `infrastructure`,
   no `application`, no SDKs).
3. `application/` does not import `api` or `infrastructure`.

Implemented with stdlib `ast` + `pathlib` rather than adding `import-linter`
(minimal-dependency discipline; `import-linter` is noted as an alternative in
§18 if the rules outgrow a small script).

**Negative-control strategy (safe — no forbidden import in production code).**
The checker is written as a pure function that takes source text (or a path) and
returns the set of violating imports it finds. The tests exercise it against
**synthetic, in-test source** — a string / temp-file fixture containing e.g.
`import spikes.foo` or a `domain/` module that imports `fastapi` — asserting the
checker flags it. This proves the detector genuinely fails on a violation
**without** ever introducing a real forbidden import into `src/argus/`. The
positive control runs the same checker over the real `src/argus/**` tree and
asserts zero findings. No production module is ever modified to "prove" the test
works.

### 7.5 Coverage policy

- **Threshold: 85% line coverage on `src/argus`, enforced in CI
  (`--cov-fail-under=85`).**
- Justification: M0 code is mostly thin wiring (factory, middleware, handlers,
  settings). 100% invites coverage-gaming tests of trivial glue; <80% would let
  real branches (error mapping, readiness failure, correlation-ID fallback) go
  untested. 85% forces the meaningful branches to be covered while leaving room
  for pragmatic exclusions (`main.py` entrypoint, `__repr__`). The exact number
  is flagged in §18 as adjustable with evidence.
- `spikes/` is excluded from coverage entirely.

---

## 8. Code Quality

Tooling is chosen to **avoid duplicate tools**:

| Concern | Tool | Justification / why not the alternative |
|---------|------|-----------------------------------------|
| Lint | **Ruff** | Replaces flake8 + isort + pyupgrade + bandit-style checks in one fast tool. |
| Format | **Ruff formatter** | Same tool as lint → no Black. Avoids the Black+Ruff double-format class of conflicts; one formatter, one config. |
| Security lint (Python) | **Ruff `S` (flake8-bandit) rules** | Avoids a separate Bandit install; SAST proper is CodeQL (§11), so no third overlapping tool. |
| Type checking | **mypy (strict)** | Mature, the de-facto standard, integrates with pydantic via its mypy plugin, widely understood in interviews. Pyright is a strong alternative (faster, better inference) but ties cleanly to the Node/VS Code toolchain; mypy keeps the quality stack pure-Python and CI-simple. Choosing **one** type checker is deliberate — running both is duplicate tooling. (mypy approved in §18.) |
| Pre-commit | **pre-commit** | Runs only **fast** hooks locally: Ruff lint + Ruff format, Gitleaks, and lightweight file-hygiene hooks (trailing whitespace, end-of-file, large-file / merge-conflict / YAML-TOML checks). **No mypy on pre-commit** — strict mypy is slow and whole-tree, so it stays in `make check` and CI (§10, §13). This keeps the commit loop cheap; type errors are caught at the local pre-PR gate and in CI, not on every commit. |

Ruff and mypy configuration live in `pyproject.toml` (single config surface).
Ruff rule selection starts pragmatic (`E,F,I,UP,B,S,...`) and is tightened over
milestones rather than maxed out on day one.

---

## 9. Docker

### 9.1 Image

- **Multi-stage** build:
  - Stage 1 (builder): `python:3.12-slim`, install `uv`, `uv sync --frozen
    --no-dev --no-group test` into a venv.
  - Stage 2 (runtime): `python:3.12-slim`, copy only the venv + `src/argus`.
- **Non-root runtime**: create and switch to an unprivileged `argus` user;
  `USER argus` before `CMD`. (`docs/SECURITY.md` §15.)
- **Small/reproducible**: slim base, no build toolchain in the final stage, no
  dev/test deps, deterministic install from `uv.lock`. `python:3.12-slim` chosen
  over distroless for M0 so the image has a shell for debugging and a working
  package manager for CVE patching; distroless is flagged in §18 as a later
  hardening option.
- **Healthcheck**: `HEALTHCHECK` curling `GET /health` (the liveness endpoint,
  §4.3).
- `CMD ["uvicorn","argus.main:app","--host","0.0.0.0","--port","8000"]`.
- Build args inject `GIT_SHA` / build metadata (§14) as env for the running app.

### 9.2 `.dockerignore`

Excludes `.git`, `spikes/`, `tests/`, `docs/`, `.venv`, caches, `.env` — keeps
the build context small and guarantees no secrets or spike code enter the image.

### 9.3 Local developer workflow

- **No `docker-compose.yml` in M0.** ARGUS has exactly one runtime service at
  this milestone, so Compose would orchestrate a single container — pure
  overhead with nothing to compose. The local run is `make run` (native) or a
  plain `docker build` + `docker run` (§13), which is reproducible on its own.
- **Compose arrives in a later milestone**, when there is more than one local
  service to wire together (e.g. PostgreSQL / Redis). That is the point where
  `docker-compose.yml` earns its place; adding it now would be speculative
  infrastructure (`docs/ARCHITECTURE.md` §21).
- **No Kubernetes** in M0 (`docs/ARCHITECTURE.md` §21: K8s not before a real
  orchestration requirement). Liveness/readiness split (§4.3) keeps the door
  open at zero cost.

---

## 10. CI (GitHub Actions)

PR-triggered pipeline. Jobs ordered cheap-to-expensive so fast failures are
fast. Each check appears **once** (no duplicate scanners).

| Stage | Tool | Notes |
|-------|------|-------|
| Install deps | `uv sync --frozen` | Fails on stale lock (reproducibility). |
| Lint + format check | `ruff check` + `ruff format --check` | One tool, two modes. |
| Type check | `mypy` | Strict. |
| Unit tests | `pytest tests/unit` | Fast, deterministic. |
| Integration/API tests | `pytest tests/integration tests/architecture` | TestClient + import-boundary. |
| Coverage | `pytest --cov=argus --cov-fail-under=85` | Combined run gates coverage (§7.5). |
| Secret scan | **Gitleaks** | On the diff/history. Also a pre-commit hook (§8). |
| Dependency vuln scan | **pip-audit** | Audits locked Python deps against PyPA advisory DB. |
| SAST | **CodeQL** | Separate `codeql.yml` workflow (§11). |
| Docker build | `docker build` | Proves the image builds from a clean checkout. |
| Container vuln scan | **Trivy (image)** | Scans the built image for OS/library CVEs. |

Scanner ownership (each layer has exactly one authority — no redundant scans):

- **No Bandit** — Ruff `S` rules cover it; CodeQL is the deeper SAST.
- **pip-audit owns Python dependency vulnerabilities.** It audits the locked
  Python deps against the PyPA advisory DB and is the single authority for that
  layer.
- **Trivy in M0 is the built-container-image vulnerability gate only.** It scans
  the image produced by `docker build` for OS/base-image + system-library CVEs —
  the layer pip-audit cannot see. **Trivy filesystem/repo scanning is
  deliberately not run in M0**: it would re-scan the same Python deps pip-audit
  already owns, adding noise without coverage. The two are complementary (Python
  deps vs. image/OS layer), not duplicate. Filesystem mode is added only if a
  later, specific gap justifies it.
- One lint/format tool, one type checker, one secret scanner, one SAST, one
  Python dependency auditor, one container-image scanner.

CI must pass **from a clean checkout** (acceptance criterion §15).

---

## 11. Security Baseline

| Tool | Protects against | Where it runs |
|------|------------------|---------------|
| **Gitleaks** | Committed secrets / credentials in diffs and history (`docs/SECURITY.md` §10). | pre-commit (local) + CI (every PR). |
| **pip-audit** | Known-vulnerable Python dependencies (PyPA advisory DB), per locked versions (`docs/SECURITY.md` §14). | CI (every PR) + available via `make security`. |
| **CodeQL** | SAST — code-level vulnerability patterns (injection, unsafe deserialization, etc.) in ARGUS's own Python. | Dedicated GitHub Actions workflow on PR + scheduled. |
| **Trivy** | OS/base-image + library CVEs in the built container image (`docs/SECURITY.md` §15). | CI, after Docker build. |
| **Dependabot** | Outdated/vulnerable dependencies and un-pinned GitHub Actions; opens update PRs. | GitHub-native, scheduled (`.github/dependabot.yml`). |

This set maps directly onto the planned controls already written in
`docs/SECURITY.md` §14. M0 wires them up; it does not invent new ones.

---

## 12. Supply-Chain Hygiene

- **Pinned/reproducible deps**: `uv.lock` committed; `--frozen` installs in CI
  and Docker (§3.4).
- **Dependency updates**: Dependabot for the `pip`/`uv` ecosystem **and** for
  `github-actions` (so Action pins get bumped with provenance).
- **Least-privilege GitHub Actions permissions**: every workflow sets top-level
  `permissions: contents: read` and elevates per-job only where required
  (e.g. CodeQL needs `security-events: write`). No default write tokens.
- **Third-party Actions pinned to commit SHAs**, not floating tags — Dependabot
  keeps the SHAs current. First-party `actions/*` may use major-version tags.
- **Future SBOM path**: Trivy can emit CycloneDX/SPDX from the image; M0 does
  **not** generate/publish an SBOM yet (no releases to attach it to). The hook
  point is documented so SBOM generation is an additive step when releases exist
  — matching `docs/SECURITY.md` §14 ("SBOM later").
- **No unnecessary production packages** — §3.3 runtime list is minimal and
  justified; LangGraph/DB/AI SDKs are explicitly excluded.

---

## 13. Developer Experience

Smallest useful command surface via a **Makefile** (no new build tool just for
convenience — `make` is ubiquitous and zero-install on the dev platforms):

| Command | Does |
|---------|------|
| `make setup` | `uv sync` (all groups) + `pre-commit install`. |
| `make run` | `uvicorn argus.main:app --reload`. |
| `make test` | `pytest` with coverage. |
| `make lint` | `ruff check` + `ruff format --check`. |
| `make fmt` | `ruff format` + `ruff check --fix`. |
| `make typecheck` | `mypy`. |
| `make security` | `gitleaks detect` + `pip-audit`. |
| `make check` | lint + typecheck + test (the local pre-PR gate; mirrors CI). |

The Makefile only wraps `uv`/tool invocations — it adds no logic. A task runner
(nox/tox/invoke) is deliberately **not** added; it would be speculative for a
single-env project.

---

## 14. Versioning / Build Metadata

- **Application version**: single source in `src/argus/__init__.py`
  (`__version__`), referenced by `pyproject.toml` (`dynamic = ["version"]`) and
  resolved at runtime via `importlib.metadata.version("argus")`. No duplicate
  version strings.
- **Git SHA / build metadata**: injected at container build via `ARG GIT_SHA`
  (and optional build time) → env var → read by settings/observability.
  Absent in local dev → reported as `"unknown"` / `"dev"` (graceful).
- **Environment**: `ARGUS_ENVIRONMENT` (`dev` | `staging` | `production`),
  validated (§5).
- Exposed via `GET /version` → `{"version","git_sha","environment"}` and stamped
  onto every log line (§6) and the startup banner. Non-sensitive by design.

---

## 15. Acceptance Criteria (objective, testable)

M0 is complete only when **all** of the following pass from a clean checkout:

1. `make setup` performs a clean install from scratch (`uv sync --frozen`
   succeeds; lock is not stale).
2. `make run` starts the API; `GET /health` returns `200`.
3. `GET /ready` returns `200`; readiness check registry works (unit +
   integration tests pass).
4. `GET /version` returns version + environment (+ git SHA when built in Docker).
5. All quality gates pass: `ruff check`, `ruff format --check`, `mypy` (strict),
   `pytest` with **coverage ≥ 85%**.
6. Architecture tests pass: **no production module imports from `spikes/`**;
   domain-layer purity holds; layer direction holds.
7. Docker image builds and **runs as a non-root user**; container `HEALTHCHECK`
   reports healthy.
8. Secret scan (Gitleaks) reports **no findings**; `.env` is git-ignored;
   `.env.example` contains only placeholders.
9. Dependency scan (pip-audit), SAST (CodeQL) and container scan (Trivy) pass
   according to the documented policy (no unresolved High/Critical without a
   recorded, reviewed exception).
10. CI passes end-to-end from a clean checkout on a PR into `main`.

Each criterion has a corresponding automated check (test, CI job, or scan) —
"the agent finished" is not acceptance (`docs/ENGINEERING_LOOP.md` §10).

---

## 16. Explicit Non-Goals

M0 does **not** implement, and PRs adding these will be rejected as scope creep:
threat-intelligence logic, IOC investigation logic, LangGraph workflows, agents,
RAG, vector search, PostgreSQL schemas/migrations, Redis, MCP, frontend,
Kubernetes, cloud deployment, model-provider calls, authn/authz business logic.

Permitted only where strictly required for foundation architecture: **tiny
interfaces/stubs** — e.g. an empty `domain/`/`application/` package with a port
Protocol used by a test, or a readiness-check registry with zero registered
checks. Any stub must be inert (no behavior, no dependency) and justified in its
PR. Nothing is copied from `spikes/` into production without explicit review
(governing principle; ADR-002 notes spike code is evidence, not source).

---

## 17. Proposed Implementation Sequence

Small, independently reviewable slices (`docs/ENGINEERING_LOOP.md` §17: avoid one
uncontrolled AI change). Each slice is its own commit/PR-sized unit on
`feat/m0-production-foundation`.

### Slice 1 — Project skeleton + tooling config
- **Purpose**: `src/` layout, empty layers, `pyproject.toml`, `uv.lock`, Ruff +
  mypy config, `.gitignore`, `.env.example`. App not required to run yet.
- **Files**: `pyproject.toml`, `uv.lock`, `src/argus/__init__.py` (+ empty layer
  packages), `.env.example`, `.gitignore`.
- **Verify**: `uv sync --frozen`; `ruff check`; `python -c "import argus"`.
- **Accept**: clean install works; package imports; version resolves.

### Slice 2 — Typed settings + config
- **Purpose**: `config/settings.py`, fail-fast validation, `ARGUS_` env prefix.
- **Files**: `src/argus/config/settings.py`, `tests/unit/test_settings.py`.
- **Verify**: `pytest tests/unit/test_settings.py`; `mypy`.
- **Accept**: invalid env fails fast with non-secret message; defaults typed.

### Slice 3 — Observability / logging baseline
- **Purpose**: structlog JSON logging, service/version/environment fields,
  correlation-id contextvar.
- **Files**: `src/argus/observability/logging.py`, `tests/unit/test_logging.py`.
- **Verify**: `pytest tests/unit/test_logging.py`.
- **Accept**: log lines carry required fields; no secret leakage; dev vs prod
  renderer switch works.

### Slice 4 — FastAPI factory + system endpoints + error model + correlation middleware
- **Purpose**: `create_app()`, lifespan, `/health` `/ready` `/version`, error
  envelope + handlers, request-ID middleware.
- **Files**: `src/argus/api/app.py`, `api/errors.py`, `api/middleware.py`,
  `api/v1/router.py`, `api/v1/system.py`, `src/argus/main.py`,
  `tests/integration/test_system_endpoints.py`,
  `tests/integration/test_errors.py`.
- **Verify**: `pytest tests/integration`; `make run` + curl health/ready/version.
- **Accept**: endpoints return specified shapes; correlation ID echoed;
  unhandled error returns generic 500 + correlation ID, no stack trace.

### Slice 5 — Architecture / import-boundary tests + coverage gate
- **Purpose**: enforce layering and **no-import-from-spikes**; wire coverage.
- **Files**: `tests/architecture/test_import_boundaries.py`, pytest/coverage
  config in `pyproject.toml`.
- **Verify**: `pytest tests/architecture`; `pytest --cov-fail-under=85`.
- **Accept**: boundary tests pass over the real `src/argus/**` tree (positive
  control) **and** the checker provably flags violations fed as synthetic
  in-test source — `import spikes.*`, a `domain/` module importing `fastapi`
  (negative control, §7.4). No real forbidden import is ever added to production
  code to prove the test. Coverage gate active.

### Slice 6 — Docker + .dockerignore
- **Purpose**: multi-stage non-root image, healthcheck. No Compose (§9.3).
- **Files**: `Dockerfile`, `.dockerignore`.
- **Verify**: `docker build .`; `docker run` + hit `/health`; confirm `whoami`
  inside container is non-root; confirm `spikes/` absent from image.
- **Accept**: image builds reproducibly, runs as non-root, healthcheck healthy.

### Slice 7 — Makefile + pre-commit
- **Purpose**: developer command surface + local hooks.
- **Files**: `Makefile`, `.pre-commit-config.yaml`.
- **Verify**: `make check`; `pre-commit run --all-files`.
- **Accept**: all `make` targets work; pre-commit runs only fast hooks (Ruff
  lint+format, Gitleaks, file-hygiene) — no mypy on pre-commit (§8); strict mypy
  runs in `make check` / CI.

### Slice 8 — CI pipeline
- **Purpose**: `.github/workflows/ci.yml` with all §10 stages,
  least-privilege permissions, SHA-pinned third-party Actions.
- **Files**: `.github/workflows/ci.yml`.
- **Verify**: PR triggers pipeline; all jobs green from clean checkout.
- **Accept**: every §10 stage present exactly once; permissions scoped.

### Slice 9 — Security + supply-chain wiring
- **Purpose**: CodeQL workflow, Dependabot (pip + actions), Trivy image scan,
  pip-audit, Gitleaks in CI.
- **Files**: `.github/workflows/codeql.yml`, `.github/dependabot.yml`,
  scan steps in `ci.yml`.
- **Verify**: scans run on PR and pass per policy.
- **Accept**: §11 tools all active and wired to the documented policy.

### Slice 10 — README + M0 wrap-up docs
- **Purpose**: fill the empty `README.md` (quickstart, command surface, layout),
  note M0 completion against §15.
- **Files**: `README.md`.
- **Verify**: a new developer can follow README to run + test from scratch.
- **Accept**: all §15 acceptance criteria demonstrably met and documented.

---

## 18. Decisions and Risks

### 18.1 Resolved decisions (human architecture review — approved)

These decisions have cost, lock-in, or policy implications and were reviewed and
**approved** by a human (`docs/ENGINEERING_LOOP.md` §2, §16). The builder
implements them as written; it does not re-open them.

| # | Decision | Approved outcome |
|---|----------|------------------|
| 1 | **Python minor** | **3.12**, pinned `>=3.12,<3.13` (§2). |
| 2 | **Package / dependency management** | **`uv`** with a committed `uv.lock`; `--frozen` installs in CI and Docker (§3). |
| 3 | **Lint + formatting** | **Ruff only** (lint + formatter); no Black, no flake8/isort/Bandit (§8). |
| 4 | **Type checker** | **mypy, strict** — single checker (§8). Full strict mypy runs in `make check` and CI, **not** on pre-commit (§8, §13). |
| 5 | **Structured-logging dep** | **`structlog`** (§3.3, §6). |
| 6 | **Testing** | **pytest** (+ `pytest-cov`, `httpx`) (§7). |
| 7 | **Coverage threshold** | **85%** line coverage on `src/argus`, enforced in CI (§7.5). Adjust later only with evidence. |
| 8 | **Container base** | **`python:3.12-slim`** for M0; distroless remains a later hardening option (§9.1). |
| 9 | **Pre-commit** | **Yes** — fast hooks only (Ruff lint+format, Gitleaks, file-hygiene); no mypy on pre-commit (§8). |
| 10 | **Security tooling** | **Gitleaks** (secrets), **pip-audit** (Python deps), **CodeQL** (SAST), **Trivy** (built container image), **Dependabot** (deps + GitHub Actions) (§11). |
| 11 | **Scanner responsibility** | **pip-audit owns Python dependency vulnerabilities; Trivy in M0 is the built-image CVE gate only.** No Trivy filesystem/repo scanning in M0 — complementary, not duplicate (§10). |
| 12 | **Container registry / image publishing** | **None in M0** — build-only, no registry/push, no SBOM publishing yet (§12). |
| 13 | **Kubernetes / cloud deployment** | **None in M0** (§9.3, §16). |
| 14 | **LangGraph in production** | **Not integrated in M0** — orchestration stays behind interfaces for a later milestone (§0.1, ADR-002). |
| 15 | **No local Compose in M0** | **No `docker-compose.yml`** — one runtime service; Compose added in a later milestone when multiple local services exist (§9.3). |
| 16 | **Project license + metadata** | **TBD** — a genuinely open future call (18.2), but it **does not block M0**. M0 ships with license unset / `TBD` in `pyproject.toml`; resolving it is additive. |

### 18.2 Genuinely unresolved (future decisions — not required for M0)

These remain open but are **not blockers** for M0. They are recorded so they are
not silently decided by the builder; each is picked up when its milestone or a
real requirement arrives.

| # | Decision | Status / default |
|---|----------|------------------|
| A | **Project license** | Still TBD (human/legal call). Resolving it later only edits metadata (`pyproject.toml`, future SBOM); it does not change M0 code. |
| B | **CI cost / runner policy** (scheduled CodeQL, Trivy DB pulls) | Default: GitHub-hosted, PR + weekly schedule. Revisit if org billing/minutes policy requires. |
| C | **Distroless / image hardening** | Deferred hardening option beyond the approved `slim` base (§9.1). |
| D | **Trivy filesystem mode** | Not run in M0; add only if a specific, justified gap appears (§10). |
| E | **`import-linter`** | Stdlib `ast` script suffices for M0; adopt only if boundary rules outgrow it (§7.4). |
| F | **SBOM generation/publishing** | Deferred until releases exist to attach it to (§12). |

No expensive or high-lock-in infrastructure (K8s, cloud, managed DB, vector DB,
orchestration framework) is decided here. Those remain in
`docs/ARCHITECTURE.md` §24 and their own future ADRs.

---

## 19. Traceability

- Repo layering ← `docs/ARCHITECTURE.md` §17.
- No-LangGraph-in-M0 ← ADR-002 consequences + `docs/ARCHITECTURE.md` §5
  (orchestration behind an interface, later milestone).
- Python 3.12 ← `spikes/orchestration/RESULTS.md` §7 (3.14 deprecation warnings).
- Deterministic / 0-paid-call tests ← `docs/EVALUATION.md`;
  `spikes/orchestration/RESULTS.md` (33/33, 0 paid calls).
- Security tooling set ← `docs/SECURITY.md` §10, §14, §15, §16.
- Secure-failure error model, secret handling ← `docs/SECURITY.md` §10, §11.
- Correlation IDs / audit readiness ← `docs/ARCHITECTURE.md` §19,
  `docs/SECURITY.md` §12.
- Small reviewable slices, human gate ← `docs/ENGINEERING_LOOP.md` §2, §10, §17.
```
