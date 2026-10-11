"""Typed vocabulary of the agent loop. Framework-independent; pydantic v2.

These types carry no orchestration behavior (no loop/retry/transition decisions)
— that lives in :mod:`argus.orchestration.graph`. Evidence is deliberately *not*
re-modelled here: the loop stores M1 :class:`~argus.domain.evidence.EvidenceRecord`
objects so provenance and the fact/claim split are preserved end to end.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from argus.orchestration.state import InvestigationState

# Bound on model-supplied free text. The model's rationale is DATA only — it is
# recorded for inspectability and never interpreted as an instruction (T-TOOL-003,
# T-AI-006). Bounding it closes an oversize/DoS vector at the model boundary.
_MAX_NOTE = 512
_MAX_ARG = 512


class ToolName(StrEnum):
    """Tools the investigator may propose. Deny-by-default: a name here is only
    *executable* if the active :class:`~argus.orchestration.policy.ToolPolicy`
    allowlists it."""

    LOOKUP_IP = "lookup_ip"
    LOOKUP_DOMAIN = "lookup_domain"
    # Sensitive / privileged action. Carries no collection value; it exists to
    # exercise the approval and unauthorized-tool paths (HITL + T-TOOL-001).
    EXPORT_INTEL = "export_intel"


class ToolStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


class OrchestrationStatus(StrEnum):
    """Status of the *agent loop* (distinct from the deterministic M1
    ``InvestigationStatus`` lifecycle). Describes workflow, not threat level."""

    PLANNING = "planning"
    COLLECTING = "collecting"
    VERIFYING = "verifying"
    WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"
    FAILED = "failed"


class TerminationReason(StrEnum):
    """Why the loop stopped. Exactly one is set on every terminal path."""

    SUFFICIENT_EVIDENCE = "sufficient_evidence"
    MAX_ITERATIONS = "max_iterations"
    RETRY_EXHAUSTED = "retry_exhausted"
    REJECTED_BY_HUMAN = "rejected_by_human"
    POLICY_DENIED = "policy_denied"
    # Model concluded without decisive evidence and with no further action to
    # propose. An explicit, enumerated stop — never an implicit fall-through.
    NO_ACTIONABLE_STEP = "no_actionable_step"
    # The model could not produce a usable decision (provider error/timeout,
    # refusal, empty, or schema-invalid output). Distinct from NO_ACTIONABLE_STEP
    # so a *tooling* failure is never mistaken for the model deciding to stop
    # (T-AI-004: untrusted model output fails safe, it is not acted on).
    MODEL_UNAVAILABLE = "model_unavailable"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class AgentAction(StrEnum):
    """Shape of a model proposal: reach for a tool, or stop.

    ``ABORT`` is not a shape the *model* ever emits — the structured decision
    schema only offers ``PROPOSE_TOOL``/``CONCLUDE``. It is the adapter's safe
    signal that no usable decision could be obtained (provider error, refusal,
    empty or schema-invalid output); the graph maps it to an explicit
    ``MODEL_UNAVAILABLE`` terminal rather than fabricating a next step."""

    PROPOSE_TOOL = "propose_tool"
    CONCLUDE = "conclude"
    ABORT = "abort"


class ToolRequest(BaseModel):
    """A proposed tool invocation. The model supplies the *intent* (tool + args);
    identity (``request_id``) is minted deterministically by the graph so the
    model cannot control it (T-AI-006)."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    tool_name: ToolName
    arguments: dict[str, str] = Field(default_factory=dict)
    requested_by: str = "investigator"

    @field_validator("arguments")
    @classmethod
    def _bound_arguments(cls, value: dict[str, str]) -> dict[str, str]:
        for key, item in value.items():
            if not 1 <= len(key) <= _MAX_ARG or len(item) > _MAX_ARG:
                raise ValueError(f"tool argument out of bounds: {key!r}")
        return value


class ToolExecution(BaseModel):
    """Audit record of one executed (or attempted) tool call. Separate from the
    evidence it produced: evidence identity/provenance lives on each
    :class:`~argus.domain.evidence.EvidenceRecord`; this is the call log."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    tool_name: ToolName
    status: ToolStatus
    attempt: int
    error: str | None = None
    evidence_ids: tuple[str, ...] = ()
    at: datetime  # injected collection clock (never the wall clock) — determinism


class AgentDecision(BaseModel):
    """What the model proposes next. ``note`` is the model's rationale — stored
    for inspectability, treated strictly as data."""

    model_config = ConfigDict(frozen=True)

    action: AgentAction
    tool_name: ToolName | None = None
    note: str = ""

    @field_validator("note")
    @classmethod
    def _bound_note(cls, value: str) -> str:
        if len(value) > _MAX_NOTE:
            raise ValueError(f"note must be at most {_MAX_NOTE} chars")
        return value

    @model_validator(mode="after")
    def _require_tool_for_proposal(self) -> AgentDecision:
        if self.action is AgentAction.PROPOSE_TOOL and self.tool_name is None:
            raise ValueError("PROPOSE_TOOL requires a tool_name")
        # Only a tool proposal carries a tool_name; CONCLUDE and ABORT never do.
        if self.action is not AgentAction.PROPOSE_TOOL and self.tool_name is not None:
            raise ValueError(f"{self.action.value} must not carry a tool_name")
        return self


class AuditEvent(BaseModel):
    """One observable timeline entry. No secrets, no chain-of-thought — just the
    deterministic step, its decision detail, and when it happened."""

    model_config = ConfigDict(frozen=True)

    step: str
    detail: dict[str, object] = Field(default_factory=dict)
    at: datetime  # injected clock (never the wall clock) — determinism


@runtime_checkable
class InvestigatorModel(Protocol):
    """Port the agent loop calls to get the next proposed action.

    The *only* place model reasoning enters the loop. Its output is untrusted
    (T-AI-004): the graph validates, authorizes and bounds whatever it proposes.
    Implementations are injected at the composition root; a deterministic
    stand-in drives it in tests (no live provider in M2 Slice 1)."""

    def propose_next_action(self, state: InvestigationState) -> AgentDecision: ...
