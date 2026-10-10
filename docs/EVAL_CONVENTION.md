# ARGUS — Agent Evaluation Convention (M2+)

The minimum reusable convention for evaluating agent behavior. It is deliberately
small: deterministic scenario evals as ordinary `pytest`, reusing the shapes the
orchestration spike already proved. This is the operational "how"; the broader
strategy lives in [`EVALUATION.md`](EVALUATION.md), which this convention serves.

**No external evaluation platform, no paid model calls, no new dependency** until a
later milestone (`EVALUATION.md` §19, M6) clearly justifies one.

## 1. What an agent eval verifies

Each scenario is a deterministic assertion over one agent run. At minimum the
convention supports verifying:

- **expected tool selection** — the agent chose the right tool(s) for the input;
- **forbidden tool execution** — a disallowed tool is never executed;
- **workflow completion** — the run reaches the expected terminal status;
- **stop reason** — the explicit, enumerated termination reason matches;
- **repeated-action prevention** — no duplicate/no-progress tool call loop;
- **evidence attribution / integrity** — evidence carries correct subject,
  provenance and investigation association; nothing fabricated;
- **unauthorized tool execution rate** — denied/forbidden tool requests result in
  zero executions (rate = 0).

## 2. Scenario shape

Scenarios are data, assertions are shared. This mirrors
`spikes/orchestration/shared/scenarios.py` + `shared/models.py` (proven: 33/33
tests, 0 paid calls) — reuse those types rather than inventing new ones. A scenario
declares, as typed data:

| Field | Meaning |
|-------|---------|
| `scenario_id` | stable identifier |
| `input` / `input_type` | the observable fed to the agent |
| `expected_tools` | tools that should be selected/executed |
| `forbidden_tools` | tools that must never execute |
| `expected_status` | expected terminal lifecycle status |
| `expected_stop_reason` | enumerated termination reason |
| `max_tool_calls` | upper bound asserted against actual calls |
| `expected_evidence` | subject/provenance expectations (attribution, no fabrication) |
| `allow_unauthorized` | always `false`; unauthorized executions must be 0 |
| `notes` | human context |

The agent run is driven with **deterministic/mock tools and a deterministic model
stand-in** — never a live provider (`AGENTS.md`: determinism; no network, no paid
API in tests).

## 3. Where eval cases live

- Scenario evals: `tests/eval/` (deterministic `pytest`, collected by the existing
  `make test` / CI gate — no separate runner).
- Prefer one parametrized fixture over the scenario table (as the spike does), so a
  new case is one data row, not new test code.
- A successful adversarial attack (prompt injection, unauthorized tool request,
  loop/cost abuse) becomes a regression scenario here (`SECURITY.md` §18,
  `EVALUATION.md` §10).

## 4. Minimum gate for an agent-behavior change

A change to the agent loop, tool selection/execution, orchestration state or HITL
is not done until:

1. the relevant `tests/eval/` scenarios pass deterministically (no paid calls);
2. the seven verifications in §1 hold for the paths the change touches;
3. `agentic-ai-review` has run;
4. any new attack discovered during review is captured as a regression scenario.

## 5. Deliberately out of scope (for now)

- No LLM-as-judge, no RAG/retrieval metrics, no cost/latency benchmarking harness —
  those arrive with their milestones (`EVALUATION.md` §5, §12, §19).
- No eval dashboard or gold-dataset platform (M6).
- No live-provider evals in the PR gate.
