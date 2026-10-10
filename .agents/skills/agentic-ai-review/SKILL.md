---
name: agentic-ai-review
description: Review of agentic AI code (the investigation loop, tool selection/execution, model-output handling, orchestration state, HITL) for M2+. Treats model output as untrusted input; checks tool-authority separation, bounded iteration, provenance integrity, explicit stop reasons, and decision evaluability.
---

# Agentic AI Review

**Trigger:** the change touches the agent/investigation loop, tool selection or
execution, model-output handling, orchestration state, retries/iteration, or
human-in-the-loop (M2+). Starts applying with the M2 Agentic Investigator
([`docs/milestones/M2_AGENTIC_INVESTIGATOR.md`](../../../docs/milestones/M2_AGENTIC_INVESTIGATOR.md)).

Distinct from `security-review` (owns threat exposure of any surface) and
`cyber-domain-review` (owns IOC semantics): this skill owns the **agentic control
properties** — the places where a model's output influences what the system does.

## Inputs

- The diff.
- Agentic threat IDs: `T-AI-*`, `T-TOOL-*` in [`docs/SECURITY.md`](../../../docs/SECURITY.md) §6–§8.
- Orchestration decisions and bounds: [`docs/adr/002-agent-orchestration-framework.md`](../../../docs/adr/002-agent-orchestration-framework.md);
  the proven deterministic shapes in `spikes/orchestration/shared/`
  (`policy.py`, `models.py`, `limits.py`, `state.py`).
- Eval convention for agent behavior: [`docs/EVAL_CONVENTION.md`](../../../docs/EVAL_CONVENTION.md).
- Loop/HITL architecture: [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) §5, §14, §15, §16.

## Checklist

1. **Model output is untrusted input.** Every model/tool output is validated by
   deterministic code before it influences control flow or becomes evidence. No
   raw model string is executed, trusted, or stored as fact (`T-AI-004`).
2. **Tool schema validation.** Tool arguments are validated against a typed schema
   *before* execution; malformed arguments are rejected, not coerced (`T-TOOL-002`).
3. **Authorization lives outside prompts.** A deterministic `ToolPolicy`
   (deny-by-default allowlist) decides execution — never the model, never prompt
   text (`T-TOOL-001`, `T-AI-006`). Order is `schema → policy → (approval) → execute`.
4. **Tool allowlist.** Only allowlisted tools are reachable; a non-allowlisted
   request is denied and recorded, never executed.
5. **Prompt-injection / tool-authority separation.** Instructions found in
   retrieved content or tool output cannot grant authority, change the allowlist,
   or skip approval. Authority is structural, not textual.
6. **Bounded iterations / retries.** Loop iterations and tool retries are capped by
   deterministic control code (reuse `MAX_INVESTIGATION_ITERATIONS`,
   `MAX_TOOL_RETRIES`), not by model judgement. No path can loop unbounded
   (`T-AI-005`, cost/DoS).
7. **Repeated-action protection.** The same tool call with the same arguments is
   not re-issued in a loop; duplicate/no-progress actions are detected and halt or
   escalate.
8. **Evidence / provenance integrity.** Raw vs normalized values stay distinct;
   each evidence record keeps its source, trust level and reference. Association is
   validated (right subject, right investigation); nothing cross-contaminates.
9. **Fabricated-evidence prevention.** A model may propose a claim; a claim becomes
   evidence only through the deterministic evidence path with real provenance.
   Failures become FAILURE evidence records — never invented data, never dropped.
10. **HITL boundaries.** Sensitive actions pause for human approval; rejection is
    terminal (stop-after-reject is structural, not a defended special case);
    pause/resume preserves state.
11. **Side-effects, idempotency, resume safety.** Side-effecting steps are
    idempotent or guarded so a retry or a resume-after-pause cannot double-execute
    or corrupt state.
12. **Explicit stop reasons.** Every terminal state carries an explicit,
    enumerated termination reason (`sufficient_evidence`, `max_iterations`,
    `retry_exhausted`, `policy_denied`, `rejected_by_human`, …) — never an
    implicit or inferred stop.
13. **Model / tool failure observability.** Model errors, malformed output, tool
    failures, policy denials and approvals are recorded on the inspectable state
    timeline (events), so a run can be audited and replayed.
14. **Agent decision evaluability.** Tool selection, the chosen next action, and
    the stop reason are captured in typed state so the deterministic scenario evals
    in [`docs/EVAL_CONVENTION.md`](../../../docs/EVAL_CONVENTION.md) can assert on them.

## Stopping conditions

- Every applicable item above is satisfied with evidence in code/tests/state, and
  the relevant scenario evals pass → done; hand off.
- An agentic-control ambiguity or a HIGH-risk agency concern
  ([`ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §9) → stop and escalate
  the specific case to the human; never self-approve it.

## Must not

- Let model/tool output govern authorization, bounds, or the allowlist.
- Accept an unbounded or model-bounded loop/retry.
- Allow a model-asserted value to become evidence without deterministic provenance.
- Approve its own change or a HIGH-risk agency change.
- Weaken or suppress a gate to pass.
