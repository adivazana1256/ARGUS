# ARGUS — Agent Instructions

Standing instructions for any AI agent working in this repository. Rules and
pointers only — the "why" lives in the linked docs. Read those; do not expect
this file to repeat them.

## Prime directive

> The LLM is not the source of truth. Evidence is.

You may reason, plan and draft. Deterministic controls, tests, scans and
collected evidence decide whether a change is correct. A passing opinion is not
a passing gate. See [`README.md`](README.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Hard prohibitions (no exceptions without explicit human approval)

- No `git commit`, `git push`, `git merge`, tag, release, or deploy.
- No weakening a security or quality gate to pass: no lowering the coverage
  threshold, loosening Ruff/mypy config, `# noqa`/`# type: ignore`/`--no-verify`,
  skipping tests, or suppressing a scanner finding.
- You **may** read, implement and verify changes locally, and propose a diff.

The human owns the gate. See [`docs/ENGINEERING_LOOP.md`](docs/ENGINEERING_LOOP.md) §2, §10, §17.

## Current scope (M1)

M1 = the **deterministic cyber core** (IOC type detection, normalization,
validation, evidence model, deterministic risk triage), built as small vertical
slices. Out of scope — do not add: agent framework, LangGraph, MCP, RAG, vector
DB, PostgreSQL, model-provider calls, authn/authz logic, frontend, Kubernetes.
See [`docs/milestones/M0_PRODUCTION_FOUNDATION.md`](docs/milestones/M0_PRODUCTION_FOUNDATION.md) §16 and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §24.

## Standing rules

- **Plan first.** Before a non-trivial change, produce the short plan from
  [`docs/ENGINEERING_LOOP.md`](docs/ENGINEERING_LOOP.md) §4 (files, interfaces,
  tests, risks, assumptions). Flag any ADR / trust-boundary / API-contract /
  storage change *before* coding (§5 Step 2).
- **Tests alongside behavior**, never after. Design the test and eval cases with
  the implementation.
- **Architecture boundaries hold.** Inner never imports outer; `domain/` is
  stdlib + pydantic only. Enforced by `tests/architecture/`. See
  [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §1.1.
- **Determinism.** No network, no wall-clock, no randomness-without-seed, no paid
  API in tests ([`README.md`](README.md) Testing; M0 §7).
- **Bounded loops.** `MAX_AUTONOMOUS_REPAIR_ITERATIONS = 3`. After 3 failed
  repair cycles: stop, preserve failure evidence, summarize, escalate to the
  human ([`docs/ENGINEERING_LOOP.md`](docs/ENGINEERING_LOOP.md) §7).
- **Investigate, don't suppress.** A security or scanner finding is investigated
  and fixed at root cause, not silenced.
- **"Agent finished" is not Done.** Done = [`docs/ENGINEERING_LOOP.md`](docs/ENGINEERING_LOOP.md) §10.

## Skills — load only when the trigger applies

Playbooks in `.agents/skills/`. Load the one whose trigger matches; don't load all.

- **`code-change-verification`** — after writing/modifying `src/` or `tests/`
  code, or after a repair attempt. Runs the local gate; bounded repair loop.
- **`cyber-domain-review`** — any change to IOC detection/normalization/validation,
  the evidence model, or deterministic risk triage. Semantic edge cases, FP/FN,
  normalization invariants, provenance, determinism, regression/eval capture.
- **`security-review`** — change touches external input, a trust boundary,
  secrets, SSRF/network, auth(z), tool/agent surfaces, deployment, or error/log
  output.
- **`pr-readiness`** — change believed complete, before handing to the human gate.
  Assembles the evidence package and halts.
