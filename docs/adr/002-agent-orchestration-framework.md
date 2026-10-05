# ADR-002 — Agent Orchestration Framework

- Status: Accepted
- Date: 2026-10-05

## Decision

ARGUS will use **LangGraph** as its primary agent orchestration framework for
bounded, evidence-driven cyber investigations.

The OpenAI Agents SDK was evaluated as a strong alternative and was not selected
as the primary orchestrator. This is a fit decision for ARGUS's current
requirements, not a judgment that the Agents SDK is inferior in general.

## Context

ARGUS requires an orchestration layer for bounded, evidence-driven cyber
investigations.

The orchestration layer must support:

- explicit investigation state
- multi-step workflows
- specialized agents
- tool calling
- branching
- bounded loops
- retries and failure handling
- human-in-the-loop interruption
- pause and resume
- structured outputs
- MCP integration
- observability
- testing
- evaluation
- security controls

Because orchestration is a core architectural dependency, ARGUS does not select a
framework based on popularity or developer familiarity. ARGUS's governing
architectural rule (see `docs/ARCHITECTURE.md`) is that AI may reason about
evidence, but evidence and deterministic controls govern system behavior. The
security model (see `docs/SECURITY.md`) treats LLM output as untrusted until
validated by deterministic controls, and requires that authorization never move
into model prompts. The orchestration framework must make these properties
natural to express, inspect and test.

To ground the decision in evidence rather than assumption, an architecture spike
implemented the same investigation workflow in both candidate frameworks against
identical shared domain models, mock tools, scenarios and assertions. See
[`spikes/orchestration/SPEC.md`](../../spikes/orchestration/SPEC.md) for the
spike design and
[`spikes/orchestration/RESULTS.md`](../../spikes/orchestration/RESULTS.md) for
the measured results.

## Candidates

1. LangGraph
2. OpenAI Agents SDK

## Evaluation Criteria

Both candidates were evaluated against the same criteria. These criteria are
retained from the original spike proposal because they remain the basis for the
decision.

### 1. Workflow Explicitness

Can an engineer understand the investigation flow from the code? Are transitions
visible, loops explicit, stopping conditions obvious, and invalid transitions
preventable?

### 2. State Management

Typed state, state persistence, pause/resume, investigation recovery, state
inspection, reproducibility.

### 3. Human-in-the-Loop

Interruption model, approval requests, persistence while paused, resume behavior,
developer complexity.

### 4. Tool Control

Typed tool arguments, tool validation, authorization hooks, tool filtering,
approval before execution, failure handling.

### 5. Failure Handling

Retries, timeouts, malformed model output, tool failure, maximum iterations,
recovery behavior.

### 6. MCP

MCP client integration, tool discovery, tool filtering, approval controls,
security boundaries, implementation complexity.

### 7. Observability

Traces, agent visibility, tool-call visibility, state-transition visibility,
custom telemetry integration, OpenTelemetry compatibility.

### 8. Testing

Unit-test ergonomics, deterministic workflow testing, mockability,
state-transition testing, tool testing, regression testing.

### 9. Evaluation Integration

How easily ARGUS can record model version, prompt version, workflow version, tool
calls, investigation steps, tokens, latency, cost, and final verdict.

### 10. Provider Portability

Dependency on one model provider, custom model support, ability to route models,
impact on the ARGUS Model Gateway.

### 11. Framework Complexity

Amount of framework-specific code, hidden behavior, learning curve, debugging
complexity, architectural lock-in.

### 12. Security Fit

Whether deterministic ARGUS security controls can remain outside model authority.
The framework must not force authorization decisions into prompts.

Scores alone do not determine the winner. Security, workflow control and
maintainability may outweigh total score.

## Spike Evidence

The spike was independently reviewed and verified. The following is observed
evidence; full detail lives in
[`spikes/orchestration/RESULTS.md`](../../spikes/orchestration/RESULTS.md).

- **33/33 automated tests passed** across both frameworks (6 scenarios plus
  shared unit tests), with **0 paid model/API calls** required by the suite.
- Both implementations were tested against equivalent external scenarios using
  the same shared assertions, and produced identical investigation outcomes
  (status, termination reason, tool-execution counts, verdict).
- The deterministic `ToolPolicy` remained **outside model authority in both
  implementations**. The model could not override authorization in either
  framework.
- Bounded execution was demonstrated in both: investigation iterations never
  exceeded `MAX_INVESTIGATION_ITERATIONS` (3), tool retries never exceeded
  `MAX_TOOL_RETRIES` (2), and no infinite loops occurred.
- **LangGraph** expressed state transitions, bounded investigation loops, retry
  control, termination and human-in-the-loop explicitly in the graph (nodes and
  conditional edges).
- **OpenAI Agents SDK** successfully demonstrated native tool execution,
  interruption, approval/rejection and resume.
- The Agents SDK implementation required a deterministic fake model
  (~104 LOC) to reproduce model-driven loop decisions without real model calls.
  LangGraph required no equivalent.
- In the Agents SDK adapter, some final termination classification is normalized
  after execution from observed run state, rather than being expressed directly
  as control flow.
- Agents SDK rejection required explicit handling to guarantee
  stop-after-rejection; otherwise the model-driven loop re-proposed the tool and
  re-triggered approval.
- The Agents SDK has attractive native OpenAI/MCP integration.
- Python 3.14 produced dependency deprecation warnings during the spike; these
  were warnings only and did not fail any tests.

Per-criterion observations from the spike (1–5, narrow spike observations, not a
verdict): LangGraph scored higher on workflow explicitness (5 vs 3), provider
portability (5 vs 2), testing (5 vs 4), and security fit (5 vs 4). The two were
comparable on human-in-the-loop (4/4), tool control (4/4), observability (4/4)
and evaluation integration (4/4). Orchestration-proper LOC was comparable
(~250–290 effective lines each); the Agents SDK carried the additional fake-model
code on top.

## Why LangGraph Was Selected

LangGraph is the better fit for ARGUS's current requirements, in priority order:

1. **Explicit deterministic workflow control.** The investigation flow is a
   literal node/edge graph. Transitions, branches, retries and stopping
   conditions are deterministic control code, not emergent behavior of a model's
   tool-calling loop. This matches the bounded investigation loop described in
   `docs/ARCHITECTURE.md`.

2. **Security-sensitive bounded execution.** Iteration caps, retry caps and
   termination are enforced by graph edges — deterministic application code the
   model cannot override. This directly supports the controls for excessive
   agency (T-AI-005) and recursive-loop/cost-abuse threats in `docs/SECURITY.md`,
   and keeps authorization (`ToolPolicy`) outside the model.

3. **Inspectable state transitions.** Typed `InvestigationState` is the graph's
   state schema. `get_state` and stream snapshots make the current step and
   transition history directly observable, supporting the auditable state
   transitions required by the Investigation Service.

4. **Deterministic testing.** The full suite runs deterministically with no paid
   calls and no fake-model shim. This lowers the cost of the regression-test
   discipline ARGUS requires (successful attacks become regression tests).

5. **HITL control.** Pause/resume is expressed explicitly via `interrupt()` and
   `Command(resume=…)`, with checkpointer-backed state persistence across the
   pause. Rejection is a conditional edge to a terminal node — stop-after-reject
   is structural, not something that must be defended against.

6. **Maintainability and debuggability.** One primary abstraction (`StateGraph`)
   governs the flow. For evidence-driven investigations, a graph an engineer can
   read top-to-bottom is easier to reason about, extend and debug at 3am than an
   implicit model-driven loop.

## Why the OpenAI Agents SDK Was Not Selected as Primary Orchestrator

The OpenAI Agents SDK is a strong, capable framework. It demonstrated native tool
execution, clean interruption/approval/resume, and first-class MCP support. It is
simply a **less natural fit for ARGUS's current requirement for explicit
deterministic control flow**:

- Its model is agent-centric: the investigation loop, retries and bounding are
  driven by the model's tool-calling behavior plus `max_turns`, rather than by
  explicit control code. The shared tests proved the *outcomes* are identical;
  the *mechanism* provides looser separation between deterministic control and
  model behavior.
- Running the suite without a provider required a custom `Model` implementation
  (~104 LOC). This is direct evidence of model-provider coupling that conflicts
  with the ARGUS Model Gateway goal of not depending on one provider.
- Stop-after-rejection and some final termination classification required
  explicit handling / post-hoc normalization rather than being expressed
  directly in control flow.

None of these are defects. They reflect a different design philosophy that is
well-suited to agent-led tasks, but less aligned with ARGUS's present need for
inspectable, deterministic, security-bounded workflows.

## Trade-offs

- **Determinism over model-native ergonomics.** LangGraph requires explicitly
  wiring the graph; the Agents SDK offers more out-of-the-box agent behavior.
  ARGUS values the explicit wiring.
- **MCP integration effort.** The Agents SDK has richer native MCP support
  (`HostedMCPTool`, `MCPToolApprovalFunction`). With LangGraph, MCP tools are
  adapted into node-callable tools and authorization remains in ARGUS's
  deterministic layer. This is more integration work but keeps authority where
  ARGUS wants it.
- **Provider breadth.** The Agents SDK leans toward the OpenAI ecosystem;
  LangGraph nodes are provider-agnostic plain functions. ARGUS prefers provider
  neutrality.

## Consequences

- The AI Orchestration Layer (`docs/ARCHITECTURE.md` §5) will be implemented with
  LangGraph, behind an interface so domain logic does not depend on it directly.
- `InvestigationState` becomes the LangGraph state schema; investigation lifecycle
  states map onto graph nodes/edges.
- Production use of the LangGraph checkpointer requires registering custom
  Pydantic types (`allowed_msgpack_modules`) to avoid the deserialization
  warnings observed in the spike.
- MCP tool integration must include an ARGUS-owned authorization wrapper rather
  than delegating approval/filtering to the SDK/MCP layer.
- `docs/ARCHITECTURE.md` §24 (open decisions) can mark "LangGraph vs OpenAI Agents
  SDK" resolved; this is tracked separately and not changed by this ADR.

## Security Implications

- Authorization stays outside the model. `ToolPolicy` is deterministic
  application code; LangGraph does not pull authorization into prompts
  (supports T-TOOL-001, T-AI-006, Security Fit criterion).
- Bounded execution (max iterations, max retries, explicit termination) is
  enforced by graph edges, mitigating excessive agency (T-AI-005) and
  recursive-loop / cost-abuse DoS (SECURITY §13).
- HITL pause/resume for sensitive tools is structural, supporting
  `docs/ARCHITECTURE.md` §16 and the approval requirements in SECURITY.
- State transitions are inspectable and auditable, supporting the audit
  requirements in SECURITY §12.
- Tool output and retrieved content remain untrusted; normalization happens in
  ARGUS code after the deterministic policy gate, not inside the orchestrator.

## Testing Implications

- The orchestration layer can be tested deterministically with no paid model
  calls, matching the spike (33/33, 0 paid calls).
- State transitions, retries, termination reasons and policy denials are directly
  assertable against typed state.
- No fake-model shim is required for LangGraph, reducing test-harness surface
  area compared with the Agents SDK path.
- Abuse-case scenarios (unauthorized tool, approval rejection, max iterations,
  retry exhaustion) are expressible as regression tests, supporting SECURITY §18.

## Provider Portability Implications

- LangGraph nodes are provider-agnostic plain functions, aligning with the ARGUS
  Model Gateway (`docs/ARCHITECTURE.md` §13) goal of not binding application code
  to one provider.
- Model routing, fallback and token/cost accounting can live in the Gateway
  behind the nodes, rather than being coupled to the orchestrator.
- This avoids the provider coupling observed with the Agents SDK, which needed a
  custom `Model` to run without a provider.

## MCP Implications

- No MCP server was built in the spike (per SPEC); integration shape was
  documented only.
- With LangGraph, MCP tools are adapted into node-callable tools, and ARGUS's
  deterministic `ToolPolicy` wraps execution. There is no framework coupling to
  MCP specifically.
- The Agents SDK's richer native MCP support is acknowledged; if ARGUS later
  wants that surface, approval/filtering must still be reconciled with ARGUS's
  external `ToolPolicy` so authority does not move into the SDK/MCP layer.
- MCP-specific threats (T-TOOL-004, T-TOOL-005) remain mitigated by ARGUS-owned
  authorization, allow-lists and approved-server configuration.

## Conditions That Would Cause This ADR to Be Revisited

- ARGUS shifts from explicit deterministic workflows toward predominantly
  agent-led, open-ended investigation where model-driven control is preferred.
- Native MCP ergonomics or OpenAI-ecosystem integration become a dominant
  requirement that outweighs explicit control.
- LangGraph's maintenance, licensing, stability or performance degrades
  materially, or production experience contradicts the spike's findings on state
  persistence, observability or debuggability.
- Evaluation results show the deterministic-graph approach measurably harms
  investigation quality versus a model-driven loop.
- A provider-portability regression in LangGraph undermines the Model Gateway
  goal.

## References

- [`spikes/orchestration/SPEC.md`](../../spikes/orchestration/SPEC.md) — spike
  design, scenarios, and acceptance criteria.
- [`spikes/orchestration/RESULTS.md`](../../spikes/orchestration/RESULTS.md) —
  measured comparison evidence (test outcomes, LOC, per-criterion observations,
  difficulties log).
- `docs/ARCHITECTURE.md` — AI Orchestration Layer (§5), Investigation Loop (§15),
  HITL (§16), Model Gateway (§13).
- `docs/SECURITY.md` — LLM-output-untrusted principle, T-AI-005, T-TOOL-001/004/005,
  DoS/cost abuse (§13).
