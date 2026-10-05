"""Agent, tools and the RunBox that carries deterministic state through an SDK run.

Authorization is enforced here as ordinary code: the SDK's native approval
mechanism (needs_approval) is wired to the shared ToolPolicy, and DENY is enforced
inside the tool body before the mock tool runs. The model never owns the policy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from agents import Agent, function_tool

from shared import rules
from shared.models import (
    AuditEvent,
    Evidence,
    IOCType,
    PolicyDecision,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)
from shared.policy import SchemaValidationError, ToolPolicy, validate_schema
from shared.tools import ScriptedToolProvider

from .fake_model import DeterministicFakeModel


@dataclass
class RunBox:
    """Mutable deterministic state shared between the tool closures and the fake
    model within one SDK run. Lives in the adapter, not in SDK-serialized state,
    so it survives pause/resume (same closures reused)."""

    inv_id: str
    raw_ioc: str
    ioc_type: IOCType
    proposed_tool: ToolName
    provider: ScriptedToolProvider
    policy: ToolPolicy

    attempts: int = 0  # real mock-tool executions
    last_status: ToolStatus | None = None
    denied: bool = False
    rejected: bool = False  # set by adapter when a human rejects approval
    evidence: list[Evidence] = field(default_factory=list)
    tool_history: list[ToolRequest] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    events: list[AuditEvent] = field(default_factory=list)

    def record(self, step: str, **detail) -> None:
        self.events.append(AuditEvent(step=step, detail=dict(detail)))

    def make_request(self) -> ToolRequest:
        return ToolRequest(
            request_id=f"{self.inv_id}-req-{len(self.tool_history)}",
            tool_name=self.proposed_tool,
            arguments={"target": self.raw_ioc},
        )


def build_agent(box: RunBox) -> Agent:
    """Construct the investigator Agent with one policy-guarded tool."""

    async def _needs_approval(ctx, args, call_id) -> bool:
        # Native SDK approval, but the DECISION is the shared deterministic policy.
        req = box.make_request()
        return box.policy.evaluate(req) == PolicyDecision.APPROVAL_REQUIRED

    @function_tool(
        name_override=box.proposed_tool.value,
        needs_approval=_needs_approval,
    )
    def threat_intel_tool(target: str) -> str:
        req = box.make_request()
        box.tool_history.append(req)
        box.record("select_tool", tool=req.tool_name.value)

        # Schema validation + deterministic authorization BEFORE execution.
        try:
            validate_schema(req)
        except SchemaValidationError as exc:
            box.denied = True
            box.record("schema_invalid", error=str(exc))
            return json.dumps({"blocked": "schema_invalid"})

        decision = box.policy.evaluate(req)
        box.record("policy_check", tool=req.tool_name.value, decision=decision.value)
        if decision == PolicyDecision.DENY:
            box.denied = True
            box.record("policy_denied", tool=req.tool_name.value)
            return json.dumps({"blocked": "policy_denied"})

        # Authorized (or approved via SDK interruption) -> run the mock tool.
        result = box.provider.run(req)
        box.attempts += 1
        box.last_status = result.status
        box.tool_results.append(result)
        box.record(
            "execute_tool",
            tool=req.tool_name.value,
            attempt=box.attempts,
            status=result.status.value,
        )
        if result.status == ToolStatus.SUCCESS:
            ev = rules.normalize_evidence(result)
            box.evidence.append(ev)
            box.record("store_evidence", evidence_id=ev.evidence_id)
            return json.dumps(result.raw_payload)
        return json.dumps({"failure": result.error})

    return Agent(
        name="investigator",
        instructions=(
            "You investigate a security IOC by calling the threat-intelligence "
            "tool until the evidence is decisive, then conclude."
        ),
        tools=[threat_intel_tool],
        model=DeterministicFakeModel(box),
    )
