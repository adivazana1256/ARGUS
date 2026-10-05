"""InvestigationState: the typed, serializable state object both frameworks
read and write. Serializability is required for LangGraph checkpointing and for
OpenAI-side pause/resume parity.

This module holds the state SHAPE and small, side-effect-free helpers for
recording events. It holds NO orchestration logic (no loop, retry or transition
decisions) — those belong to each framework adapter.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import (
    AuditEvent,
    Evidence,
    InvestigationInput,
    InvestigationPlan,
    InvestigationStatus,
    PolicyDecision,
    TerminationReason,
    ToolRequest,
    ToolResult,
    Verdict,
    VerificationResult,
)


class InvestigationState(BaseModel):
    investigation_id: str
    input: InvestigationInput
    status: InvestigationStatus = InvestigationStatus.CREATED

    plan: InvestigationPlan | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    tool_history: list[ToolRequest] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)

    iteration: int = 0
    retries: dict[str, int] = Field(default_factory=dict)

    pending_approval: ToolRequest | None = None

    # Transient working fields (used by adapters that keep the in-flight request
    # on the state object, e.g. the LangGraph graph). Not all adapters use them.
    current_request: ToolRequest | None = None
    policy_decision: PolicyDecision | None = None

    verification: VerificationResult | None = None
    verdict: Verdict | None = None
    termination_reason: TerminationReason | None = None

    events: list[AuditEvent] = Field(default_factory=list)

    def record(self, step: str, **detail: object) -> None:
        """Append an observable event. Pure bookkeeping, no control flow."""
        self.events.append(AuditEvent(step=step, detail=dict(detail)))
