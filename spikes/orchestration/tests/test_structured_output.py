"""Structured-output validation: verdicts/plans/verification conform to the
shared Pydantic schemas, for both frameworks."""

from __future__ import annotations

from shared.models import InvestigationPlan, VerificationResult, Verdict
from shared.scenarios import by_id


def test_completed_investigation_has_valid_structured_output(orchestrator):
    out = orchestrator.run(by_id()["S1"])
    state = out.state

    assert isinstance(state.plan, InvestigationPlan)
    assert isinstance(state.verification, VerificationResult)
    assert isinstance(state.verdict, Verdict)

    v = state.verdict
    assert v.classification in {"malicious", "suspicious", "benign", "inconclusive"}
    assert 0.0 <= v.confidence <= 1.0
    # material verdict is backed by evidence ids (groundedness, T-AI-004)
    assert v.evidence_ids
    assert set(v.evidence_ids) <= {e.evidence_id for e in state.evidence}
