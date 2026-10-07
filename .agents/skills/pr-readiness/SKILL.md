---
name: pr-readiness
description: Assemble the deterministic evidence package for the human gate and halt. Enforces that no agent commits, pushes, merges, or deploys without explicit human approval.
---

# PR Readiness

**Trigger:** the change is believed complete, before handing to the human gate.

**Goal:** give the human everything needed to approve — then stop. This skill is
the enforcement point for the no-commit/push/merge rule.

## Inputs

- The diff and the outputs of `code-change-verification` (and
  `cyber-domain-review` / `security-review` if their triggers applied).
- Human gate + PR requirements: [`docs/ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §10, §12.
- Definition of Done: [`docs/ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §10.
- Risk classification: [`docs/ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §9.
- CI gates it must pass once pushed: [`M0`](../../../docs/milestones/M0_PRODUCTION_FOUNDATION.md) §10.

## Checklist

1. Classify risk LOW / MEDIUM / HIGH ([`ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §9).
2. Confirm which reviews actually ran and passed:
   - `code-change-verification` green (gate output present);
   - `cyber-domain-review` if IOC/evidence code changed;
   - `security-review` if a security surface changed.
   A missing-but-required review → route back to that skill; do not paper over.
3. Confirm Definition of Done items ([`ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §10).
4. Draft the PR narrative answering [`ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §12:
   what changed, why, how, how tested, security impact, eval/arch impact, known
   limitations.
5. List unresolved risks explicitly — including anything flagged HIGH for the
   human. Do not inflate claims beyond what was tested
   ([`SECURITY.md`](../../../docs/SECURITY.md) §21).
6. Confirm work is on a `feat|fix|docs/*` branch, not `main`
   ([`ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §11).

## Stopping conditions

- Evidence package presented to the human with an explicit "awaiting approval"
  → **halt**.

## Must not

- Run `git commit`, `git push`, `git merge`, `gh pr create`, `gh pr merge`, tag,
  or deploy.
- Declare the change "done" or merge it.
- Hide, omit, or downplay a failed or skipped gate.
- Claim behavior that was not tested.
