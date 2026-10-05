"""The investigation workflow as a LangGraph StateGraph.

Every node reads domain answers from the shared layer; the GRAPH expresses the
orchestration: transitions, the bounded loop (conditional edges), retry edges and
the dynamic HITL interrupt. None of that control flow lives in shared code.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from shared import rules
from shared.limits import MAX_INVESTIGATION_ITERATIONS, MAX_TOOL_RETRIES
from shared.models import (
    InvestigationStatus,
    PolicyDecision,
    TerminationReason,
    ToolName,
    ToolStatus,
)
from shared.policy import SchemaValidationError, ToolPolicy, validate_schema
from shared.state import InvestigationState
from shared.tools import ScriptedToolProvider


def build_investigation_graph(
    provider: ScriptedToolProvider,
    policy: ToolPolicy,
    proposed_tool: ToolName,
):
    """Compile the workflow. Config (provider/policy/proposed tool) is captured in
    closures — it is not part of the serializable investigation state."""

    # --- nodes ------------------------------------------------------------- #
    def plan(state: InvestigationState) -> dict:
        plan = rules.build_plan(state.input)
        return {
            "plan": plan,
            "status": InvestigationStatus.COLLECTING_EVIDENCE,
            "events": state.events + [_ev("plan", objective=plan.objective)],
        }

    def select_tool(state: InvestigationState) -> dict:
        req = rules.make_tool_request(state, proposed_tool)
        return {
            "current_request": req,
            "iteration": state.iteration + 1,
            "tool_history": state.tool_history + [req],
            "events": state.events
            + [_ev("select_tool", tool=req.tool_name.value, iteration=state.iteration + 1)],
        }

    def policy_check(state: InvestigationState) -> dict:
        req = state.current_request
        try:
            validate_schema(req)
        except SchemaValidationError as exc:
            return {
                "policy_decision": PolicyDecision.DENY,
                "events": state.events + [_ev("schema_invalid", error=str(exc))],
            }
        decision = policy.evaluate(req)
        return {
            "policy_decision": decision,
            "events": state.events
            + [_ev("policy_check", tool=req.tool_name.value, decision=decision.value)],
        }

    def mark_pause(state: InvestigationState) -> dict:
        # Record the pending approval BEFORE interrupting so the paused snapshot
        # is observable.
        return {
            "pending_approval": state.current_request,
            "status": InvestigationStatus.WAITING_FOR_HUMAN,
            "events": state.events
            + [_ev("approval_requested", tool=state.current_request.tool_name.value)],
        }

    def approval_gate(state: InvestigationState) -> dict:
        decision = interrupt(
            {"approval_for": state.current_request.tool_name.value}
        )
        return {
            "events": state.events + [_ev("approval_decision", decision=str(decision))],
            # stash decision for the router via a transient field reuse
            "policy_decision": (
                PolicyDecision.ALLOW
                if str(decision).lower() in ("approve", "approvaldecision.approve")
                else PolicyDecision.DENY
            ),
        }

    def execute_tool(state: InvestigationState) -> dict:
        req = state.current_request
        attempts = state.retries.get(req.tool_name.value, 0)
        result = provider.run(req)
        attempts += 1
        retries = dict(state.retries)
        retries[req.tool_name.value] = attempts
        events = state.events + [
            _ev(
                "execute_tool",
                tool=req.tool_name.value,
                attempt=attempts,
                status=result.status.value,
            )
        ]
        update = {
            "tool_results": state.tool_results + [result],
            "retries": retries,
            "pending_approval": None,
            "status": InvestigationStatus.COLLECTING_EVIDENCE,
            "events": events,
        }
        if result.status == ToolStatus.SUCCESS:
            evidence = rules.normalize_evidence(result)
            update["evidence"] = state.evidence + [evidence]
            update["events"] = events + [
                _ev("store_evidence", evidence_id=evidence.evidence_id)
            ]
        return update

    def verify(state: InvestigationState) -> dict:
        v = rules.verify_evidence(state)
        return {
            "verification": v,
            "status": InvestigationStatus.VERIFYING,
            "events": state.events + [_ev("verify", sufficient=v.sufficient)],
        }

    def produce_verdict(state: InvestigationState) -> dict:
        sufficient = rules.evidence_sufficient(state)
        verdict = rules.synthesize_verdict(state)
        reason = (
            TerminationReason.SUFFICIENT_EVIDENCE
            if sufficient
            else TerminationReason.MAX_ITERATIONS
        )
        return {
            "verdict": verdict,
            "termination_reason": reason,
            "status": InvestigationStatus.COMPLETED,
            "events": state.events
            + [_ev("verdict", classification=verdict.classification, reason=reason.value)],
        }

    def deny(state: InvestigationState) -> dict:
        return {
            "termination_reason": TerminationReason.POLICY_DENIED,
            "status": InvestigationStatus.FAILED,
            "pending_approval": None,
            "events": state.events
            + [_ev("policy_denied", tool=state.current_request.tool_name.value)],
        }

    def retry_exhausted(state: InvestigationState) -> dict:
        return {
            "termination_reason": TerminationReason.RETRY_EXHAUSTED,
            "status": InvestigationStatus.FAILED,
            "events": state.events + [_ev("retry_exhausted")],
        }

    def rejected(state: InvestigationState) -> dict:
        return {
            "termination_reason": TerminationReason.REJECTED_BY_HUMAN,
            "status": InvestigationStatus.FAILED,
            "pending_approval": None,
            "events": state.events + [_ev("approval_rejected")],
        }

    # --- routers ----------------------------------------------------------- #
    def route_policy(state: InvestigationState) -> str:
        d = state.policy_decision
        if d == PolicyDecision.DENY:
            return "deny"
        if d == PolicyDecision.APPROVAL_REQUIRED:
            return "mark_pause"
        return "execute_tool"

    def route_after_gate(state: InvestigationState) -> str:
        # approval_gate re-used policy_decision: ALLOW => approved.
        return "execute_tool" if state.policy_decision == PolicyDecision.ALLOW else "rejected"

    def route_after_execute(state: InvestigationState) -> str:
        last = state.tool_results[-1]
        if last.status == ToolStatus.FAILURE:
            attempts = state.retries.get(last.tool_name.value, 0)
            if attempts < 1 + MAX_TOOL_RETRIES:
                return "execute_tool"  # bounded retry
            return "retry_exhausted"
        return "verify"

    def route_completion(state: InvestigationState) -> str:
        if rules.evidence_sufficient(state):
            return "produce_verdict"
        if state.iteration >= MAX_INVESTIGATION_ITERATIONS:
            return "produce_verdict"
        return "select_tool"  # bounded loop

    # --- wiring ------------------------------------------------------------ #
    g = StateGraph(InvestigationState)
    for name, fn in [
        ("plan", plan),
        ("select_tool", select_tool),
        ("policy_check", policy_check),
        ("mark_pause", mark_pause),
        ("approval_gate", approval_gate),
        ("execute_tool", execute_tool),
        ("verify", verify),
        ("produce_verdict", produce_verdict),
        ("deny", deny),
        ("retry_exhausted", retry_exhausted),
        ("rejected", rejected),
    ]:
        g.add_node(name, fn)

    g.add_edge(START, "plan")
    g.add_edge("plan", "select_tool")
    g.add_edge("select_tool", "policy_check")
    g.add_conditional_edges(
        "policy_check", route_policy, ["deny", "mark_pause", "execute_tool"]
    )
    g.add_edge("mark_pause", "approval_gate")
    g.add_conditional_edges(
        "approval_gate", route_after_gate, ["execute_tool", "rejected"]
    )
    g.add_conditional_edges(
        "execute_tool", route_after_execute, ["execute_tool", "verify", "retry_exhausted"]
    )
    g.add_conditional_edges(
        "verify", route_completion, ["select_tool", "produce_verdict"]
    )
    g.add_edge("produce_verdict", END)
    g.add_edge("deny", END)
    g.add_edge("retry_exhausted", END)
    g.add_edge("rejected", END)

    return g.compile(checkpointer=MemorySaver())


def _ev(step: str, **detail):
    from shared.models import AuditEvent

    return AuditEvent(step=step, detail=dict(detail))
