"""Uniform orchestrator interface both framework adapters implement.

This is a thin boundary, NOT an engine: it only defines how the test harness
starts a run and resumes a paused one. All loop/retry/transition/HITL behavior
lives inside each adapter's framework-native code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .models import ApprovalDecision
from .state import InvestigationState


@dataclass
class RunOutcome:
    """Result of a run or resume. `handle` is an opaque framework-specific token
    (e.g. a LangGraph thread config) the same adapter uses to resume."""

    state: InvestigationState
    handle: dict[str, object] = field(default_factory=dict)

    @property
    def paused(self) -> bool:
        return self.state.pending_approval is not None


@runtime_checkable
class Orchestrator(Protocol):
    name: str

    def run(self, scenario: "object") -> RunOutcome:
        """Start an investigation for the given Scenario."""
        ...

    def resume(self, outcome: RunOutcome, decision: ApprovalDecision) -> RunOutcome:
        """Resume a paused investigation with a human approval decision."""
        ...
