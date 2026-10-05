"""The six required scenarios, asserted identically against both frameworks via
the `orchestrator` fixture (parametrized in conftest.py)."""

from __future__ import annotations

import pytest

from shared.models import ApprovalDecision, InvestigationStatus, TerminationReason
from shared.scenarios import by_id

SCENARIOS = by_id()
# Non-interactive scenarios asserted by their final outcome.
OUTCOME_IDS = ["S1", "S2", "S3", "S3b", "S4", "S6"]


def _event_steps(state) -> list[str]:
    return [e.step for e in state.events]


@pytest.mark.parametrize("scenario_id", OUTCOME_IDS)
def test_scenario_outcome(orchestrator, scenario_id):
    sc = SCENARIOS[scenario_id]
    out = orchestrator.run(sc)
    state = out.state
    exp = sc.expected

    assert not out.paused
    assert state.status == exp.final_status
    assert state.termination_reason == exp.termination_reason
    if exp.max_tool_executions is not None:
        assert len(state.tool_results) == exp.max_tool_executions
    if exp.classification is not None:
        assert state.verdict is not None
        assert state.verdict.classification == exp.classification


def test_bounded_iterations_never_exceeded(orchestrator):
    from shared.limits import MAX_INVESTIGATION_ITERATIONS

    out = orchestrator.run(SCENARIOS["S4"])
    # one real execution per iteration; must stop at the configured maximum.
    assert len(out.state.tool_results) <= MAX_INVESTIGATION_ITERATIONS
    assert out.state.termination_reason == TerminationReason.MAX_ITERATIONS


def test_bounded_retries_never_exceeded(orchestrator):
    from shared.limits import MAX_TOOL_RETRIES

    out = orchestrator.run(SCENARIOS["S3b"])
    assert len(out.state.tool_results) == 1 + MAX_TOOL_RETRIES
    assert out.state.termination_reason == TerminationReason.RETRY_EXHAUSTED


def test_tool_failure_is_observable_then_recovers(orchestrator):
    out = orchestrator.run(SCENARIOS["S3"])
    # a failure happened and is visible, then the investigation still completed.
    statuses = [r.status.value for r in out.state.tool_results]
    assert "failure" in statuses
    assert out.state.status == InvestigationStatus.COMPLETED


def test_unauthorized_tool_blocked_and_observable(orchestrator):
    out = orchestrator.run(SCENARIOS["S6"])
    assert out.state.termination_reason == TerminationReason.POLICY_DENIED
    assert len(out.state.tool_results) == 0  # tool never executed
    assert "policy_denied" in _event_steps(out.state)  # security event observable


def test_approval_pauses_before_execution(orchestrator):
    out = orchestrator.run(SCENARIOS["S5"])
    assert out.paused
    assert out.state.status == InvestigationStatus.WAITING_FOR_HUMAN
    assert out.state.pending_approval is not None
    assert len(out.state.tool_results) == 0  # not executed while paused
    assert "approval_requested" in _event_steps(out.state)


def test_approval_resume_approve_completes(orchestrator):
    out = orchestrator.run(SCENARIOS["S5"])
    resumed = orchestrator.resume(out, ApprovalDecision.APPROVE)
    assert resumed.state.status == InvestigationStatus.COMPLETED
    assert resumed.state.termination_reason == TerminationReason.SUFFICIENT_EVIDENCE
    assert len(resumed.state.tool_results) == 1  # executed after approval
    assert resumed.state.verdict is not None


def test_approval_resume_reject_is_safe(orchestrator):
    out = orchestrator.run(SCENARIOS["S5"])
    resumed = orchestrator.resume(out, ApprovalDecision.REJECT)
    assert resumed.state.termination_reason == TerminationReason.REJECTED_BY_HUMAN
    assert len(resumed.state.tool_results) == 0  # never executed
    assert resumed.state.verdict is None
