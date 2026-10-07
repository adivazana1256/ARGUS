---
name: code-change-verification
description: Prove a code change correct locally with deterministic evidence before any review or handoff. Runs the full local gate and a bounded repair loop.
---

# Code Change Verification

**Trigger:** after writing or modifying any `src/` or `tests/` code, and after
every repair attempt.

**Goal:** deterministic, reproducible evidence that the change is correct — not
an assertion that it is.

## Inputs

- The diff under review.
- `make check` (the local gate; mirrors CI) — see [`Makefile`](../../../Makefile)
  and [`docs/milestones/M0_PRODUCTION_FOUNDATION.md`](../../../docs/milestones/M0_PRODUCTION_FOUNDATION.md) §10.
- Structured-failure format: [`docs/ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §8.

## Checklist

1. Run `make check` (`sync` → `lint` → `format-check` → `typecheck` → `test`
   with the ≥85% coverage gate). Paste the decisive output; do not summarize a
   pass you did not see.
2. On failure, write a structured failure report ([`ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §8:
   id, category, expected, actual, evidence, severity, required outcome).
3. Fix the **root cause**, not the symptom. If the failure is a real defect, add
   a regression test that reproduces it *before* fixing (see [`docs/EVALUATION.md`](../../../docs/EVALUATION.md) §18).
4. Re-run `make check`.
5. Confirm new tests are meaningful (exercise real branches/edge cases), not
   coverage-padding of trivial glue ([`M0`](../../../docs/milestones/M0_PRODUCTION_FOUNDATION.md) §7.5).
6. Confirm the diff respects layer boundaries — `tests/architecture/` stays green
   ([`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) §1.1).

## Stopping conditions

- `make check` green and new tests meaningful → done; hand off.
- **3 failed repair cycles** (`MAX_AUTONOMOUS_REPAIR_ITERATIONS = 3`) → stop,
  preserve failure evidence, summarize what was attempted, escalate to the human
  ([`ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §7).

## Must not

- Commit, push, or create a PR (that is the human gate; see `pr-readiness`).
- Lower the coverage threshold, loosen Ruff/mypy config, or edit the gate to pass.
- Add `# noqa`, `# type: ignore`, `--no-verify`, `pytest.mark.skip`, or delete a
  failing test to go green.
- Claim success without the gate output.
