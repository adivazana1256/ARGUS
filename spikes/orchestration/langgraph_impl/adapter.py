"""LangGraph adapter: implements the shared Orchestrator protocol."""

from __future__ import annotations

import uuid

from langgraph.types import Command

from shared import rules
from shared.models import ApprovalDecision, InvestigationInput
from shared.policy import ToolPolicy
from shared.runner import RunOutcome
from shared.state import InvestigationState
from shared.tools import ScriptedToolProvider

from .graph import build_investigation_graph


class LangGraphOrchestrator:
    name = "langgraph"

    def run(self, scenario) -> RunOutcome:
        provider = ScriptedToolProvider(scenario.scripts)
        policy = ToolPolicy(
            allowlist=scenario.allowlist,
            approval_required=scenario.approval_required,
        )
        app = build_investigation_graph(provider, policy, scenario.proposed_tool)

        inv_id = f"lg-{scenario.scenario_id}-{uuid.uuid4().hex[:8]}"
        initial = InvestigationState(
            investigation_id=inv_id,
            input=InvestigationInput(
                raw_value=scenario.raw_ioc,
                ioc_type=rules.detect_ioc_type(scenario.raw_ioc),
            ),
        )
        cfg = {"configurable": {"thread_id": inv_id}}
        app.invoke(initial.model_dump(), cfg)
        state = self._snapshot(app, cfg)
        return RunOutcome(state=state, handle={"app": app, "cfg": cfg})

    def resume(self, outcome: RunOutcome, decision: ApprovalDecision) -> RunOutcome:
        app = outcome.handle["app"]
        cfg = outcome.handle["cfg"]
        app.invoke(Command(resume=decision.value), cfg)
        state = self._snapshot(app, cfg)
        return RunOutcome(state=state, handle=outcome.handle)

    @staticmethod
    def _snapshot(app, cfg) -> InvestigationState:
        values = app.get_state(cfg).values
        return InvestigationState.model_validate(values)
