# ARGUS Orchestration Spike

Compares **LangGraph** and the **OpenAI Agents SDK** on the same bounded,
evidence-driven investigation workflow. Produces engineering evidence for
[ADR-002](../../docs/adr/002-agent-orchestration-framework.md). It does **not**
select a winner — that is the ADR review's job.

## Layer model (the fair-comparison contract)

- **`shared/`** — framework-independent domain layer: models, deterministic mock
  tools, `ToolPolicy` (authorization), domain rules (domain *truths* only),
  bounded-execution constants, scenarios and the `Orchestrator` protocol.
  Contains **no** loop/retry/transition/HITL control flow.
- **`langgraph_impl/`**, **`openai_agents/`** — each expresses the *orchestration*
  (state transitions, bounded loop, retry, HITL pause/resume) in its own native
  primitives. This is what the spike measures.

The hard line: shared code answers *what is true*; each framework decides *what to
do about it*. Authorization is deterministic application code outside model
authority in both.

## Run

```bash
python3 -m venv .venv
.venv/bin/python -m pip install \
  pydantic==2.13.5 langgraph==1.2.12 openai-agents==0.23.1 \
  pytest==9.1.1 pytest-asyncio==1.4.0
.venv/bin/python -m pytest -q
```

No paid model calls are made. The OpenAI Agents SDK is driven by a deterministic
fake model (`openai_agents/fake_model.py`); LangGraph nodes are plain functions.

## Scenarios (asserted identically against both)

| ID  | Name                         | Exercises                        |
|-----|------------------------------|----------------------------------|
| S1  | normal_investigation         | happy path, structured verdict   |
| S2  | insufficient_then_sufficient | bounded loop / extra step        |
| S3  | tool_failure_then_recovery   | failure visible + bounded retry  |
| S3b | retry_exhausted              | retry cap → RETRY_EXHAUSTED       |
| S4  | max_iterations               | iteration cap → MAX_ITERATIONS    |
| S5  | human_approval               | pause / resume-approve / reject  |
| S6  | unauthorized_tool            | deterministic policy DENY         |

See [RESULTS.md](./RESULTS.md) for the comparison evidence.
