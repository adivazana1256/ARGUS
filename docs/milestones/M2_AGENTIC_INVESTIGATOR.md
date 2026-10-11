# ARGUS — Milestone 2: Agentic Investigator

Status: PLANNED. This milestone specifies the work; it is not yet implemented.
It carries enough product, architecture, evaluation and security context that an
implementation prompt can be a single short paragraph.

Read alongside: [`ARCHITECTURE.md`](../ARCHITECTURE.md) §5/§6/§14/§15/§16,
[`adr/002-agent-orchestration-framework.md`](../adr/002-agent-orchestration-framework.md),
[`PRODUCT_SPEC.md`](../PRODUCT_SPEC.md) §4/§5/§7, [`SECURITY.md`](../SECURITY.md)
§6–§8, [`EVAL_CONVENTION.md`](../EVAL_CONVENTION.md). The deterministic shapes to
reuse already exist and passed the spike: `spikes/orchestration/shared/`.

## 0. Purpose

Turn the deterministic M1 investigation (parse → collect → evidence → summarize)
into a **bounded, evidence-driven agent loop**: a model proposes the next action,
deterministic controls authorize and bound it, and every decision is inspectable
and evaluable. The LLM reasons; evidence and deterministic controls govern.

M1 stays intact and deterministic. M2 wraps it — it does not rewrite it.

## 1. Scope — M2 Slice 1

In:

- An orchestrated investigation loop over the existing M1 domain, built with
  **LangGraph** (ADR-002), behind an interface so domain logic never imports it.
- Model proposes a tool action; deterministic `ToolPolicy` (deny-by-default
  allowlist, approval subset) authorizes. Order: `schema → policy → (approval) →
  execute`. Reuse `spikes/orchestration/shared/policy.py` + `models.py` shapes.
- Bounded loop: `MAX_INVESTIGATION_ITERATIONS`, `MAX_TOOL_RETRIES` as deterministic
  graph edges (reuse `shared/limits.py`). No model-bounded loops.
- Typed, inspectable `InvestigationState` with an events timeline and an explicit,
  enumerated termination reason.
- HITL: pause before a sensitive tool, resume on approve, terminate on reject
  (structural, via `interrupt()` / `Command(resume=…)`).
- Tool execution over the existing threat-intel collection contract and the offline
  mock provider only.
- `tests/eval/` scenario suite per [`EVAL_CONVENTION.md`](../EVAL_CONVENTION.md).

Out (later slices / own ADR):

- Live model calls (a deterministic model stand-in drives the loop in tests, as in
  the spike). Real provider wiring is **Slice 2** (below).
- RAG/knowledge retrieval, MCP servers, Correlation/Knowledge/Verification agents
  beyond the Investigator/Orchestrator, vector DB, PostgreSQL, Redis, frontend,
  deployment.

## 1a. Scope — M2 Slice 2 (Real LLM Investigator Adapter)

Connects the Slice 1 loop to a real, production-compatible model while keeping the
evidence-first, application-controlled authorization model intact.

In:

- A second implementation of the existing `InvestigatorModel` port,
  `infrastructure/anthropic_investigator.py`, behind the same abstraction — the
  deterministic stand-in stays the model for tests/CI and is unchanged.
- One provider (Anthropic), one model (`ARGUS_LLM_MODEL`, default `claude-opus-4-8`).
  No multi-provider/Model-Gateway abstraction yet (deferred to its own ADR; see
  `ARCHITECTURE.md` §13). The settings surface is provider-agnostic.
- **Strict structured output.** The decision is requested as a constrained JSON
  schema (action ∈ {propose_tool, conclude}, tool_name ∈ `ToolName` ∪ null, note)
  and re-validated into an `AgentDecision` here — model output is untrusted input
  (`T-AI-004`), never trusted inline.
- **Explicit failure handling.** Refusal, empty, malformed, timeout or any
  provider error (after the SDK's bounded retries) fails safe: the adapter returns
  an `AgentAction.ABORT` the graph maps to the enumerated
  `TerminationReason.MODEL_UNAVAILABLE` terminal — never a crash, a retry in the
  loop, or fabricated evidence. Distinct from `NO_ACTIONABLE_STEP` (model chose to
  stop) so a tooling failure is never mistaken for a decision.
- Secrets from settings/env only (`ARGUS_ANTHROPIC_API_KEY` as `SecretStr`); never
  logged. Observability logs the request/decision (model, iteration, action, tool,
  stop) with no secrets, no raw model text, no evidence payloads.
- Deterministic adapter tests (fake client, no network) + `tests/eval/` scenarios
  for the real-model boundary; a manual, CI-excluded smoke example
  (`examples/real_model_investigation.py`).

Out (unchanged from Slice 1 above): everything the deterministic graph, policy,
bounds, HITL and evidence path already own stays exactly as-is — this slice only
swaps *where the next proposed action comes from*. No new tools, no multi-provider
abstraction, no change to the deterministic core.

## 2. Architecture

- **Orchestration layer** (`ARCHITECTURE.md` §5) implemented with LangGraph behind
  an ARGUS-owned interface. `InvestigationState` is the graph state schema; M1
  lifecycle states map onto nodes/edges. Nodes are provider-agnostic plain
  functions (portability, ADR-002).
- **Authority stays deterministic and outside the model.** `ToolPolicy`, schema
  validation, bounds and termination are ordinary application code the model cannot
  override. Tool/retrieved output is normalized in ARGUS code *after* the policy
  gate, never trusted inline.
- **Evidence path is M1's.** The agent proposes; evidence is created only through
  the existing deterministic evidence path with real provenance. A model-asserted
  value never becomes evidence directly. Collection failures become FAILURE
  evidence records (`application/collection.py`, `application/investigation.py`).
- **Inspectability.** `get_state` / stream snapshots + the events timeline expose
  the current step, transitions, tool calls, denials, approvals and the stop reason.

## 3. Evaluation

Follow [`EVAL_CONVENTION.md`](../EVAL_CONVENTION.md). Minimum scenarios (reuse the
spike scenarios as the starting set): normal sufficient-evidence; insufficient →
sufficient; failure → recovery; retry exhausted; max iterations; approval pause →
approve; approval pause → reject; unauthorized tool denied. Each asserts tool
selection, forbidden-tool non-execution, terminal status, stop reason,
repeated-action prevention, evidence attribution/integrity, and zero unauthorized
executions. Deterministic, no paid calls, under `make test`.

## 4. Security

Primary threats and controls (`SECURITY.md`):

- `T-AI-004` model output untrusted — deterministic validation before use/storage.
- `T-AI-005` excessive agency — bounded loop/retries via graph edges.
- `T-AI-006`, `T-TOOL-001` authorization outside the model — external `ToolPolicy`.
- `T-TOOL-002` tool-argument validation — typed schema before execution.
- `T-TOOL-003` tool output inert — stored as data, never interpreted/executed.
- Prompt-injection / tool-authority separation — instructions in retrieved content
  or tool output cannot grant authority, alter the allowlist, or skip approval.
- Cost/DoS — iteration/retry caps; no unbounded path.

Every successful abuse case becomes a regression scenario (`SECURITY.md` §18).
The `agentic-ai-review` and `security-review` skills both apply to this milestone.

## 5. Definition of Done (in addition to ENGINEERING_LOOP §10)

- Loop bounded by deterministic edges; no model-bounded iteration/retry.
- Authorization, schema validation and termination are deterministic, outside the
  model, and unit-tested.
- Explicit enumerated stop reason on every terminal path.
- HITL pause/approve/reject works and is covered.
- `tests/eval/` scenarios pass deterministically with no paid calls.
- `agentic-ai-review` + `security-review` run; discovered attacks captured as
  regression scenarios.
- LangGraph confined behind the interface; `tests/architecture/` boundaries green.
