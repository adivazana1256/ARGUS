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

## Autonomy envelope

Within the prohibitions above you have maximum safe autonomy. Run the full
engineering loop end to end without re-prompting:

> inspect → plan only material decisions → implement → test/eval → independent
> reviews → bounded repair → verify → diff review → **stop at the human gate**;
> after human approval to open a PR: commit → push → PR targeting `main` → verify
> base → monitor/fix required CI and security checks → **stop at a fully green PR**.

Never merge. Never modify `main` directly. Never weaken a gate. Stop at a material
blocker or at a green, merge-ready PR — the merge is the human's.

## Current scope (M2)

M2 = the **agentic investigator** built on the deterministic M1 core. Start from
[`docs/milestones/M2_AGENTIC_INVESTIGATOR.md`](docs/milestones/M2_AGENTIC_INVESTIGATOR.md);
it carries the product, architecture, evaluation and security context so a feature
prompt can stay short.

Still out of scope until its own slice or ADR introduces it: RAG, MCP, vector DB,
PostgreSQL, Redis, new model providers, authn/authz logic, frontend, Kubernetes.
The M1 deterministic core (IOC detection, normalization, validation, evidence,
deterministic lifecycle) is complete and must stay deterministic. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) §24 and ADR-002.

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
- **Release automation.** When opening a PR: base is explicitly `main`, verify the
  base after creation, monitor the required CI + security checks, repair failures
  within the bounded loop, stop at a fully green PR. Merge is human-only. Full
  conventions: [`docs/ENGINEERING_LOOP.md`](docs/ENGINEERING_LOOP.md) §11.1.
- **Reviewer separation.** Builder, Tester, Reviewer, Security Reviewer and Eval
  Reviewer are independent roles ([`docs/ENGINEERING_LOOP.md`](docs/ENGINEERING_LOOP.md) §6).
  Run them as independent passes — the skills below, dispatched to separate
  subagents where available — with one lead agent owning integration. No custom
  multi-agent framework.

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
- **`agentic-ai-review`** — change touches the agent loop, tool selection/execution,
  model output handling, orchestration state, or HITL (M2+). Treats model output as
  untrusted; checks tool-authority separation, bounded iteration, provenance and
  stop reasons.
- **`pr-readiness`** — change believed complete, before handing to the human gate.
  Assembles the evidence package and halts.

Agent-behavior changes are evaluated with the convention in
[`docs/EVAL_CONVENTION.md`](docs/EVAL_CONVENTION.md) (deterministic scenario evals,
no paid calls).
