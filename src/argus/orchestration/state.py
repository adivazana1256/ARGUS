"""``InvestigationState`` — the typed, serializable LangGraph state schema.

Serializable because LangGraph checkpoints it (and a checkpoint is what makes
HITL pause/resume work). It holds the state SHAPE plus a pure event-recording
helper; it holds NO control flow (loop/retry/transition decisions live in
``graph.py``). Evidence is stored as real M1 ``EvidenceRecord`` objects, so a
paused-and-resumed investigation keeps full provenance.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from argus.domain.evidence import EvidenceRecord
from argus.domain.ioc import Ioc
from argus.orchestration.models import (
    AgentAction,
    AuditEvent,
    OrchestrationStatus,
    PolicyDecision,
    TerminationReason,
    ToolExecution,
    ToolRequest,
)

# Fixed, application-owned objective. Stored outside anything the model can
# write, so untrusted content cannot redirect the investigation (T-AI-006).
DEFAULT_OBJECTIVE = "Determine whether the IOC is malicious, with evidence."

# Deterministic placeholder used only when a state is constructed directly (e.g.
# in unit tests). The orchestrator injects the real investigation clock at run,
# so audit timestamps never come from the wall clock.
_DEFAULT_CLOCK = datetime(1970, 1, 1, tzinfo=UTC)


class InvestigationState(BaseModel):
    investigation_id: str
    subject: Ioc  # the validated, typed IOC under investigation
    objective: str = DEFAULT_OBJECTIVE
    status: OrchestrationStatus = OrchestrationStatus.PLANNING
    # Injected clock stamped onto every audit event — the domain/loop never reads
    # a wall clock, so a run (and a paused→resumed run) is byte-for-byte reproducible.
    clock: datetime = _DEFAULT_CLOCK

    # Evidence created only through the M1 collection path — real provenance.
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    tool_history: list[ToolRequest] = Field(default_factory=list)
    tool_executions: list[ToolExecution] = Field(default_factory=list)

    iteration: int = 0
    retries: dict[str, int] = Field(default_factory=dict)

    pending_approval: ToolRequest | None = None

    # Transient working fields the graph keeps on state between nodes.
    current_request: ToolRequest | None = None
    policy_decision: PolicyDecision | None = None
    last_action: AgentAction | None = None  # the model's most recent decision kind

    termination_reason: TerminationReason | None = None

    events: list[AuditEvent] = Field(default_factory=list)

    @field_validator("clock")
    @classmethod
    def _require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must be timezone-aware")
        return value.astimezone(UTC)

    def recorded(self, step: str, **detail: object) -> list[AuditEvent]:
        """Return the events timeline with one appended entry, stamped with the
        injected clock.

        Pure: returns a new list rather than mutating, so a graph node can put it
        straight into its state-update dict (LangGraph channels are last-write).
        """
        return [*self.events, AuditEvent(step=step, detail=dict(detail), at=self.clock)]
