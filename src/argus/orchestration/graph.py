"""The investigation workflow as a LangGraph ``StateGraph``.

This is the *only* place control flow lives. Every bound, branch, retry and the
HITL pause is an explicit node or conditional edge — deterministic application
code the model cannot override (ADR-002; T-AI-005). Nodes read domain answers
from :mod:`argus.orchestration.rules`, authorize through
:mod:`argus.orchestration.policy`, and create evidence only via the injected
:class:`~argus.orchestration.tools.ToolExecutor` (the M1 collection path).

The mandatory per-proposal order is wired structurally:

    decide -> policy_check -> (mark_pause -> approval_gate) -> execute_tool
           -> verify -> {loop back to decide | conclude}

with ``deny``, ``retry_exhausted`` and ``rejected`` as the non-happy terminals.
"""

from __future__ import annotations

from typing import cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from argus.orchestration import rules
from argus.orchestration.checkpointing import build_checkpointer
from argus.orchestration.limits import (
    MAX_INVESTIGATION_ITERATIONS,
    MAX_TOOL_RETRIES,
)
from argus.orchestration.models import (
    AgentAction,
    ApprovalDecision,
    InvestigatorModel,
    OrchestrationStatus,
    PolicyDecision,
    TerminationReason,
    ToolName,
    ToolRequest,
    ToolStatus,
)
from argus.orchestration.policy import (
    SchemaValidationError,
    ToolPolicy,
    validate_schema,
)
from argus.orchestration.state import InvestigationState
from argus.orchestration.tools import ToolExecutor

# The compiled graph's concrete generic instantiation. LangGraph's own invoke
# overloads are intricate; pinning the alias keeps our call sites typed without
# leaking that complexity across the interface.
CompiledInvestigation = CompiledStateGraph[
    InvestigationState, None, InvestigationState, InvestigationState
]


def _require_request(state: InvestigationState) -> ToolRequest:
    """The in-flight request, which ``decide`` always sets before any node that
    needs it. A missing one is an impossible-by-wiring state, surfaced loudly."""
    request = state.current_request
    if request is None:  # pragma: no cover - guaranteed set by the graph wiring
        raise RuntimeError("current_request is unexpectedly unset")
    return request


def build_investigation_graph(
    model: InvestigatorModel,
    policy: ToolPolicy,
    executor: ToolExecutor,
) -> CompiledInvestigation:
    """Compile the workflow. The model, policy and executor are captured in
    closures — they are orchestration configuration, not serializable state."""

    # --- nodes ------------------------------------------------------------- #
    def plan(state: InvestigationState) -> dict[str, object]:
        return {
            "status": OrchestrationStatus.COLLECTING,
            "events": state.recorded("plan", objective=state.objective),
        }

    def decide(state: InvestigationState) -> dict[str, object]:
        decision = model.propose_next_action(state)
        if decision.action is AgentAction.ABORT:
            # The model boundary failed safe (T-AI-004). Record the reason as DATA
            # and route to the explicit MODEL_UNAVAILABLE terminal — never retry or
            # fabricate a step. The graph, not the model, owns this stop.
            return {
                "last_action": AgentAction.ABORT,
                "events": state.recorded("decide", action="abort", note=decision.note),
            }
        if decision.action is AgentAction.CONCLUDE:
            return {
                "last_action": AgentAction.CONCLUDE,
                "events": state.recorded(
                    "decide", action="conclude", note=decision.note
                ),
            }
        # model_validator guarantees tool_name is set for a PROPOSE_TOOL action.
        tool_name = cast(ToolName, decision.tool_name)
        iteration = state.iteration + 1
        request = rules.make_tool_request(
            investigation_id=state.investigation_id,
            iteration=iteration,
            tool_name=tool_name,
            target=state.subject.normalized,
        )
        return {
            "last_action": AgentAction.PROPOSE_TOOL,
            "current_request": request,
            "iteration": iteration,
            "tool_history": [*state.tool_history, request],
            "status": OrchestrationStatus.COLLECTING,
            "events": state.recorded(
                "decide",
                action="propose_tool",
                tool=tool_name.value,
                iteration=iteration,
                note=decision.note,
            ),
        }

    def policy_check(state: InvestigationState) -> dict[str, object]:
        request = _require_request(state)
        try:
            validate_schema(request)
        # Defense-in-depth, and unreachable in Slice 1: the model proposes only a
        # tool *name* and the graph mints the arguments (T-AI-006), so a schema-
        # invalid request cannot arise yet. The gate stays wired here for the
        # slice that lets a tool take model-influenced arguments.
        except SchemaValidationError as exc:  # pragma: no cover
            return {
                "policy_decision": PolicyDecision.DENY,
                "events": state.recorded("schema_invalid", error=str(exc)),
            }
        decision = policy.evaluate(request)
        return {
            "policy_decision": decision,
            "events": state.recorded(
                "policy_check",
                tool=request.tool_name.value,
                decision=decision.value,
            ),
        }

    def mark_pause(state: InvestigationState) -> dict[str, object]:
        request = _require_request(state)
        # Record the pending approval BEFORE interrupting, so the paused snapshot
        # is observable (and survives the checkpoint).
        return {
            "pending_approval": request,
            "status": OrchestrationStatus.WAITING_FOR_HUMAN,
            "events": state.recorded(
                "approval_requested", tool=request.tool_name.value
            ),
        }

    def approval_gate(state: InvestigationState) -> dict[str, object]:
        request = _require_request(state)
        decision = interrupt(
            {
                "approval_for": request.tool_name.value,
                "request_id": request.request_id,
            }
        )
        # Default-deny: anything that is not an explicit approve is a rejection.
        approved = str(decision).strip().lower() == ApprovalDecision.APPROVE.value
        return {
            "policy_decision": (
                PolicyDecision.ALLOW if approved else PolicyDecision.DENY
            ),
            "events": state.recorded("approval_decision", approved=approved),
        }

    def execute_tool(state: InvestigationState) -> dict[str, object]:
        request = _require_request(state)
        # Retries are counted PER PROPOSAL (request_id is unique per iteration via
        # make_tool_request), not per tool name — so a tool re-proposed on a later
        # iteration starts with a fresh retry budget, and the retry loop that
        # re-executes the *same* request accumulates correctly.
        attempt = state.retries.get(request.request_id, 0) + 1
        execution, new_evidence = executor.execute(
            request,
            state.subject,
            attempt=attempt,
            investigation_id=state.investigation_id,
        )
        seen = {record.evidence_id for record in state.evidence}
        merged = [*state.evidence] + [
            record for record in new_evidence if record.evidence_id not in seen
        ]
        events = state.recorded(
            "execute_tool",
            tool=request.tool_name.value,
            attempt=attempt,
            status=execution.status.value,
        )
        return {
            "tool_executions": [*state.tool_executions, execution],
            "evidence": merged,
            "retries": {**state.retries, request.request_id: attempt},
            "pending_approval": None,
            "status": OrchestrationStatus.COLLECTING,
            "events": events,
        }

    def verify(state: InvestigationState) -> dict[str, object]:
        sufficient = rules.evidence_is_sufficient(state.evidence)
        return {
            "status": OrchestrationStatus.VERIFYING,
            "events": state.recorded("verify", sufficient=sufficient),
        }

    def conclude(state: InvestigationState) -> dict[str, object]:
        reason = rules.conclusion_reason(state.evidence, iteration=state.iteration)
        return {
            "termination_reason": reason,
            "status": OrchestrationStatus.COMPLETED,
            "pending_approval": None,
            "current_request": None,
            "events": state.recorded("conclude", reason=reason.value),
        }

    def deny(state: InvestigationState) -> dict[str, object]:
        request = state.current_request
        tool = request.tool_name.value if request else "unknown"
        return {
            "termination_reason": TerminationReason.POLICY_DENIED,
            "status": OrchestrationStatus.FAILED,
            "pending_approval": None,
            "events": state.recorded("policy_denied", tool=tool),
        }

    def retry_exhausted(state: InvestigationState) -> dict[str, object]:
        return {
            "termination_reason": TerminationReason.RETRY_EXHAUSTED,
            "status": OrchestrationStatus.FAILED,
            "events": state.recorded("retry_exhausted"),
        }

    def rejected(state: InvestigationState) -> dict[str, object]:
        return {
            "termination_reason": TerminationReason.REJECTED_BY_HUMAN,
            "status": OrchestrationStatus.FAILED,
            "pending_approval": None,
            "events": state.recorded("approval_rejected"),
        }

    def model_unavailable(state: InvestigationState) -> dict[str, object]:
        return {
            "termination_reason": TerminationReason.MODEL_UNAVAILABLE,
            "status": OrchestrationStatus.FAILED,
            "pending_approval": None,
            "current_request": None,
            "events": state.recorded("model_unavailable"),
        }

    # --- routers ----------------------------------------------------------- #
    def route_after_decide(state: InvestigationState) -> str:
        if state.last_action is AgentAction.PROPOSE_TOOL:
            return "policy_check"
        if state.last_action is AgentAction.ABORT:
            return "model_unavailable"
        return "conclude"

    def route_policy(state: InvestigationState) -> str:
        decision = state.policy_decision
        if decision is PolicyDecision.DENY:
            return "deny"
        if decision is PolicyDecision.APPROVAL_REQUIRED:
            return "mark_pause"
        return "execute_tool"

    def route_after_gate(state: InvestigationState) -> str:
        return (
            "execute_tool"
            if state.policy_decision is PolicyDecision.ALLOW
            else "rejected"
        )

    def route_after_execute(state: InvestigationState) -> str:
        last = state.tool_executions[-1]
        if last.status is ToolStatus.FAILURE:
            # Per-proposal retry budget (keyed by request_id, see execute_tool).
            # ponytail: retries re-run the same request without re-traversing the
            # approval gate. Safe in Slice 1 — the only approval-gated tool
            # (export_intel) never reaches this path. If a future approval-required
            # tool can FAIL, route its retries back through mark_pause/approval_gate.
            attempts = state.retries.get(last.request_id, 0)
            if attempts < 1 + MAX_TOOL_RETRIES:
                return "execute_tool"  # bounded retry
            return "retry_exhausted"
        return "verify"

    def route_completion(state: InvestigationState) -> str:
        if rules.evidence_is_sufficient(state.evidence):
            return "conclude"
        if state.iteration >= MAX_INVESTIGATION_ITERATIONS:
            return "conclude"
        return "decide"  # bounded loop

    # --- wiring ------------------------------------------------------------ #
    graph = StateGraph(InvestigationState)
    for name, fn in [
        ("plan", plan),
        ("decide", decide),
        ("policy_check", policy_check),
        ("mark_pause", mark_pause),
        ("approval_gate", approval_gate),
        ("execute_tool", execute_tool),
        ("verify", verify),
        ("conclude", conclude),
        ("deny", deny),
        ("retry_exhausted", retry_exhausted),
        ("rejected", rejected),
        ("model_unavailable", model_unavailable),
    ]:
        graph.add_node(name, fn)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "decide")
    graph.add_conditional_edges(
        "decide", route_after_decide, ["policy_check", "conclude", "model_unavailable"]
    )
    graph.add_conditional_edges(
        "policy_check", route_policy, ["deny", "mark_pause", "execute_tool"]
    )
    graph.add_edge("mark_pause", "approval_gate")
    graph.add_conditional_edges(
        "approval_gate", route_after_gate, ["execute_tool", "rejected"]
    )
    graph.add_conditional_edges(
        "execute_tool",
        route_after_execute,
        ["execute_tool", "verify", "retry_exhausted"],
    )
    graph.add_conditional_edges("verify", route_completion, ["decide", "conclude"])
    for terminal in (
        "conclude",
        "deny",
        "retry_exhausted",
        "rejected",
        "model_unavailable",
    ):
        graph.add_edge(terminal, END)

    return graph.compile(checkpointer=build_checkpointer())
