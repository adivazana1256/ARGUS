# ARGUS Orchestration Spike — Results

Engineering evidence for [ADR-002](../../docs/adr/002-agent-orchestration-framework.md).

- Date: 2026-10-05
- Python: 3.14.5
- Versions: `langgraph==1.2.12`, `langgraph-checkpoint==4.2.0`,
  `openai-agents==0.23.1`, `pydantic==2.13.5`, `pytest==9.1.1`
- Test result: **33 passed** (both frameworks, 6 scenarios + shared units), **0
  paid model calls**.

> This document records observed behavior only. It does **not** select a winner.

---

## 1. Test outcomes (identical assertions, both frameworks)

Every scenario below passed on **both** LangGraph and the OpenAI Agents SDK with
the same shared assertions. Values are from the live run.

| Scenario | status | termination_reason | tool executions | verdict |
|----------|--------|--------------------|-----------------|---------|
| S1 normal | completed | sufficient_evidence | 1 | malicious |
| S2 insufficient→sufficient | completed | sufficient_evidence | 2 | malicious |
| S3 failure→recovery | completed | sufficient_evidence | 2 | malicious |
| S3b retry exhausted | failed | retry_exhausted | 3 (=1+MAX_TOOL_RETRIES) | — |
| S4 max iterations | completed | max_iterations | 3 (=MAX_INVESTIGATION_ITERATIONS) | inconclusive |
| S5 approval (pause) | waiting_for_human | — | 0 | — |
| S5 → approve | completed | sufficient_evidence | 1 | malicious |
| S5 → reject | failed | rejected_by_human | 0 | — |
| S6 unauthorized | failed | policy_denied | 0 | — |

Bounded execution demonstrated: iterations never exceed 3, retries never exceed
2, no infinite loops. Authorization (`ToolPolicy`) is shared deterministic code
in both; the model cannot override it.

---

## 2. Measured size (lines of code)

Non-blank, non-comment lines unless stated. Shared layer is identical for both.

| Area | LOC |
|------|-----|
| `shared/` (models, state, tools, policy, rules, limits, runner, scenarios) | 712 total |
| LangGraph orchestration (`graph.py` + `adapter.py`) | 299 total / 253 effective |
| OpenAI Agents orchestration (`agent.py` + `adapter.py` + `fake_model.py`) | 360 total / 293 effective |
| — of which `fake_model.py` (needed only to run the SDK deterministically) | 104 total |
| Shared tests | 207 total |

Observation: orchestration-proper is comparable (~250–290 effective LOC). The SDK
carries an extra ~104 LOC for the deterministic fake model that LangGraph does not
need at all.

---

## 3. Per-criterion observations (ADR-002), score 1–5

Scores are this spike's narrow observations, not a verdict. 1=poor … 5=excellent.

| # | Criterion | LangGraph | OpenAI Agents SDK | Notes |
|---|-----------|:---------:|:-----------------:|-------|
| 1 | Workflow explicitness | 5 | 3 | LangGraph flow is a literal node/edge graph; stopping conditions are visible conditional edges. SDK flow is implicit in the model's tool-calling loop + `max_turns`. |
| 2 | State management | 4 | 3 | LangGraph persists typed state via checkpointer (pause/resume for free). SDK serializes run state (`RunState`) but domain state lived in an adapter-held `RunBox`. |
| 3 | Human-in-the-loop | 4 | 4 | Both pause before execution and resume cleanly. LangGraph: dynamic `interrupt()` + `Command(resume=…)`. SDK: native `needs_approval` → `.interruptions` → `state.approve/reject`. |
| 4 | Tool control | 4 | 4 | Both enforce schema+policy before execution. SDK's `needs_approval` accepts a callable, so policy stays the authority; DENY handled in the tool body. |
| 5 | Failure handling | 4 | 3 | LangGraph retry is an explicit conditional edge. SDK retry is model-driven (fake model re-proposes within the shared cap) + `max_turns` ceiling — looser separation. |
| 6 | MCP | n/a | n/a | Documented only, not built this spike (see §6). |
| 7 | Observability | 4 | 4 | Both emit the unified `events[]` timeline. LangGraph also exposes `get_state`/stream snapshots; SDK has built-in tracing spans (skipped without an API key). |
| 8 | Testing | 5 | 4 | Both run under one parametrized pytest fixture, no paid calls. SDK required building a fake model to be deterministic. |
| 9 | Evaluation integration | 4 | 4 | Unified `events[]` + typed state capture tool calls, steps, termination reason. Token/cost not meaningful with mock tools. |
| 10 | Provider portability | 5 | 2 | LangGraph nodes are provider-agnostic plain functions. SDK is model-centric: running without a provider required a custom `Model` implementation. |
| 11 | Framework complexity | 4 | 3 | LangGraph: one abstraction (StateGraph) to learn. SDK: Agent/Runner/Model/RunState/approval items + Responses-API output item shapes. |
| 12 | Security fit | 5 | 4 | Both keep authorization outside the model. SDK's instinct is tool-calling-in-model; keeping policy external worked but took deliberate wiring. |

---

## 4. Framework-specific abstractions used

- **LangGraph**: `StateGraph`, nodes, `add_conditional_edges`, `MemorySaver`
  checkpointer, `interrupt()`, `Command(resume=…)`. State schema = our Pydantic
  `InvestigationState` directly.
- **OpenAI Agents SDK**: `Agent`, `Runner.run_sync`, custom `Model`
  (`get_response` returning `ModelResponse` with `ResponseFunctionToolCall` /
  `ResponseOutputMessage` items), `function_tool(needs_approval=…)`,
  `RunResult.interruptions` (`ToolApprovalItem`), `RunState.approve/reject`.

## 5. HITL, retry and loop — how each did it

| Concern | LangGraph | OpenAI Agents SDK |
|---------|-----------|-------------------|
| Pause before tool | `mark_pause` node sets `pending_approval`, then `approval_gate` calls dynamic `interrupt()` | `needs_approval` callable (consults `ToolPolicy`) → Runner returns an interruption before executing |
| Resume | `invoke(Command(resume=decision), cfg)` | `state.approve/reject(item)` then `Runner.run_sync(agent, state)` |
| Reject | conditional edge → `rejected` node | adapter sets `box.rejected` so the fake model concludes instead of re-proposing |
| Retry | conditional self-edge on failure while `attempts < 1+MAX_TOOL_RETRIES` | fake model re-proposes on failure within the same shared cap; `max_turns` is the hard ceiling |
| Bounded loop | conditional edge: sufficient OR `iteration >= MAX` → verdict | fake model stops when shared `evidence_sufficient` or evidence count hits `MAX_INVESTIGATION_ITERATIONS` |

Note the asymmetry on retry/loop bounding: in LangGraph the bound is **deterministic
control code (edges)**; in the SDK the bound is **model-driven decisions** backed by
the same shared constants plus `max_turns`. The shared black-box tests prove the
*outcomes* are identical; the *mechanism* differs and is weaker on separation for
the SDK.

---

## 6. MCP (documented, not built)

Per SPEC, no MCP server was built. Observed integration shape:
- **LangGraph**: MCP tools would be adapted into node-callable tools; authorization
  would remain our deterministic layer around the call. No framework coupling to
  MCP specifically.
- **OpenAI Agents SDK**: has first-class MCP support (`HostedMCPTool`,
  `MCPToolApprovalFunction`, MCP approval items were visible in the API surface).
  Richer out-of-the-box, but approval/filtering would need to be reconciled with
  ARGUS's external `ToolPolicy` to avoid moving authority into the SDK/MCP layer.

---

## 7. Difficulties & workarounds (honest log)

1. **Package name clash** — a local package named `langgraph/` shadowed the
   installed library. Renamed to `langgraph_impl/` (deviation from SPEC tree).
2. **SDK needs a model to run** — the Agents SDK drives everything through a
   model. To keep the suite free + deterministic, implemented a custom
   `DeterministicFakeModel` (~104 LOC) returning canned tool-calls from shared
   rules. LangGraph needed nothing equivalent. This is real provider-coupling
   evidence, not hidden.
3. **SDK reject loop** — after `reject`, the fake model would re-propose the tool
   and re-trigger approval forever. Fixed with a `box.rejected` flag telling the
   model to conclude. Reveals that "stop after rejection" is not automatic in the
   model-driven loop.
4. **LangGraph checkpoint warnings** — serializing custom Pydantic types logs
   "Deserializing unregistered type…" warnings. Harmless here; silenced in test
   config. Would need `allowed_msgpack_modules` registration in production.
5. **Python 3.14** — SDK emits a `asyncio.get_event_loop_policy` DeprecationWarning
   on 3.14. Non-blocking.

---

## 8. Raw evidence index

- Live scenario table: §1 (reproduce with `pytest -q`).
- LOC: §2 (`wc -l` on each layer).
- Test suite: `tests/` — 33 tests, one parametrized fixture over both adapters.
- Observability timeline: `InvestigationState.events[]`, identical schema both
  frameworks.

**No framework selected.** Decision belongs to the ADR-002 review.
