"""OpenAI Agents SDK adapter: implements the shared Orchestrator protocol.

The SDK owns the loop (Runner/turns), tool dispatch and native approval
interruption. This adapter translates an SDK run into the shared
InvestigationState and derives the termination reason (framework-specific
orchestration) from the deterministic RunBox + shared rules/limits.
"""

from __future__ import annotations

import uuid

from agents import Runner

from shared import rules
from shared.limits import MAX_INVESTIGATION_ITERATIONS
from shared.models import (
    ApprovalDecision,
    InvestigationInput,
    InvestigationStatus,
    TerminationReason,
)
from shared.policy import ToolPolicy
from shared.runner import RunOutcome
from shared.state import InvestigationState
from shared.tools import ScriptedToolProvider

from .agent import RunBox, build_agent

# Generous hard ceiling; the domain bounds (iterations/retries) are enforced by
# the fake model via shared constants. See RESULTS.md for the asymmetry note.
_MAX_TURNS = 4 * MAX_INVESTIGATION_ITERATIONS + 6


class OpenAIAgentsOrchestrator:
    name = "openai_agents"

    def run(self, scenario) -> RunOutcome:
        inv_id = f"oa-{scenario.scenario_id}-{uuid.uuid4().hex[:8]}"
        box = RunBox(
            inv_id=inv_id,
            raw_ioc=scenario.raw_ioc,
            ioc_type=rules.detect_ioc_type(scenario.raw_ioc),
            proposed_tool=scenario.proposed_tool,
            provider=ScriptedToolProvider(scenario.scripts),
            policy=ToolPolicy(
                allowlist=scenario.allowlist,
                approval_required=scenario.approval_required,
            ),
        )
        agent = build_agent(box)
        result = Runner.run_sync(
            agent, f"Investigate IOC {scenario.raw_ioc}", max_turns=_MAX_TURNS
        )
        if result.interruptions:
            return self._paused(box, agent, result)
        return RunOutcome(state=self._final_state(box), handle={})

    def resume(self, outcome: RunOutcome, decision: ApprovalDecision) -> RunOutcome:
        box: RunBox = outcome.handle["box"]
        agent = outcome.handle["agent"]
        run_state = outcome.handle["run_state"]
        if decision == ApprovalDecision.REJECT:
            box.rejected = True  # tell the fake model to conclude, not re-propose
        for item in outcome.handle["interruptions"]:
            if decision == ApprovalDecision.APPROVE:
                run_state.approve(item)
            else:
                run_state.reject(item)
        result = Runner.run_sync(agent, run_state, max_turns=_MAX_TURNS)
        if result.interruptions:  # unexpected re-pause
            return self._paused(box, agent, result)
        if decision == ApprovalDecision.REJECT:
            state = self._final_state(box)
            state.status = InvestigationStatus.FAILED
            state.termination_reason = TerminationReason.REJECTED_BY_HUMAN
            state.verdict = None
            state.record("approval_rejected")
            return RunOutcome(state=state, handle={})
        return RunOutcome(state=self._final_state(box), handle={})

    # ------------------------------------------------------------------ #
    def _paused(self, box: RunBox, agent, result) -> RunOutcome:
        state = self._base_state(box)
        state.status = InvestigationStatus.WAITING_FOR_HUMAN
        state.pending_approval = box.make_request()
        state.record("approval_requested", tool=box.proposed_tool.value)
        return RunOutcome(
            state=state,
            handle={
                "box": box,
                "agent": agent,
                "run_state": result.to_state(),
                "interruptions": list(result.interruptions),
            },
        )

    def _base_state(self, box: RunBox) -> InvestigationState:
        state = InvestigationState(
            investigation_id=box.inv_id,
            input=InvestigationInput(raw_value=box.raw_ioc, ioc_type=box.ioc_type),
            plan=rules.build_plan(
                InvestigationInput(raw_value=box.raw_ioc, ioc_type=box.ioc_type)
            ),
            evidence=list(box.evidence),
            tool_history=list(box.tool_history),
            tool_results=list(box.tool_results),
            iteration=max(len(box.evidence), box.attempts),
            events=list(box.events),
        )
        return state

    def _final_state(self, box: RunBox) -> InvestigationState:
        state = self._base_state(box)
        state.verification = rules.verify_evidence(state)

        if box.denied:
            state.status = InvestigationStatus.FAILED
            state.termination_reason = TerminationReason.POLICY_DENIED
            return state
        if box.tool_results and not box.evidence and box.last_status is not None:
            # every real execution failed
            state.status = InvestigationStatus.FAILED
            state.termination_reason = TerminationReason.RETRY_EXHAUSTED
            return state
        if rules.evidence_sufficient(state):
            state.status = InvestigationStatus.COMPLETED
            state.termination_reason = TerminationReason.SUFFICIENT_EVIDENCE
        else:
            state.status = InvestigationStatus.COMPLETED
            state.termination_reason = TerminationReason.MAX_ITERATIONS
        state.verdict = rules.synthesize_verdict(state)
        return state
