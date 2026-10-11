"""ARGUS-owned orchestration interface + the LangGraph adapter.

The interface is a thin boundary: start a run, resume a paused one, read the
state. It exists so callers (and tests) depend on ARGUS types, never on
LangGraph — the framework is an implementation detail confined to this module
and :mod:`argus.orchestration.graph` (ADR-002: "behind an interface so domain
logic never imports it"). All loop/retry/HITL behavior lives in the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, cast, runtime_checkable

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from argus.domain.ioc import Ioc
from argus.orchestration.graph import (
    CompiledInvestigation,
    build_investigation_graph,
)
from argus.orchestration.models import ApprovalDecision, InvestigatorModel
from argus.orchestration.policy import ToolPolicy
from argus.orchestration.state import InvestigationState
from argus.orchestration.tools import ToolExecutor


@dataclass
class RunOutcome:
    """Result of a run or resume. ``handle`` is an opaque adapter-specific token
    (the LangGraph thread config) the same adapter uses to resume."""

    state: InvestigationState
    handle: dict[str, object] = field(default_factory=dict)

    @property
    def paused(self) -> bool:
        """True iff the investigation is parked waiting for a human decision."""
        return self.state.pending_approval is not None


@runtime_checkable
class InvestigationOrchestrator(Protocol):
    name: str

    def run(self, subject: Ioc, *, investigation_id: str) -> RunOutcome: ...

    def resume(self, outcome: RunOutcome, decision: ApprovalDecision) -> RunOutcome: ...


class LangGraphOrchestrator:
    """Drives an investigation through the compiled LangGraph workflow.

    The model, policy and tool executor are injected at construction (the
    composition root wires the concrete adapters), keeping authorization and the
    model stand-in swappable without touching the graph."""

    name = "langgraph"

    def __init__(
        self,
        model: InvestigatorModel,
        policy: ToolPolicy,
        executor: ToolExecutor,
    ) -> None:
        self._app: CompiledInvestigation = build_investigation_graph(
            model, policy, executor
        )
        # One injected clock, shared by tool executions and the audit timeline.
        self._now = executor.now

    def run(self, subject: Ioc, *, investigation_id: str) -> RunOutcome:
        initial = InvestigationState(
            investigation_id=investigation_id, subject=subject, clock=self._now
        )
        cfg: RunnableConfig = {"configurable": {"thread_id": investigation_id}}
        self._app.invoke(initial, cfg)
        return RunOutcome(state=self._snapshot(cfg), handle={"cfg": cfg})

    def resume(self, outcome: RunOutcome, decision: ApprovalDecision) -> RunOutcome:
        cfg = cast(RunnableConfig, outcome.handle["cfg"])
        # Resume the paused graph with the human decision (approve/reject).
        self._app.invoke(cast(Any, Command(resume=decision.value)), cfg)
        return RunOutcome(state=self._snapshot(cfg), handle=outcome.handle)

    def _snapshot(self, cfg: RunnableConfig) -> InvestigationState:
        values = self._app.get_state(cfg).values
        return InvestigationState.model_validate(values)
