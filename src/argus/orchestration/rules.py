"""Deterministic orchestration rules — the loop's domain truths.

Every function answers a control question the graph needs ("do we have enough
evidence to stop?", "what request represents this proposal?", "which enumerated
reason explains concluding?"). None of them decide *when* to loop, retry or pause
— that is graph wiring. Keeping them here (pure, importable) is what lets the
security-critical stopping logic be unit-tested outside the model and outside
LangGraph.
"""

from __future__ import annotations

from argus.application.collection import CLAIMED_VERDICT_KEY
from argus.domain.evidence import CollectionStatus, EvidenceRecord
from argus.orchestration.limits import MAX_INVESTIGATION_ITERATIONS
from argus.orchestration.models import TerminationReason, ToolName, ToolRequest

# Claimed reputations decisive enough to stop collecting. Reading a *claim* to
# decide "we have enough evidence" is a collection-sufficiency control; it does
# NOT mint an ARGUS verdict — the claim stays a claim (``docs/ARCHITECTURE.md``
# §7, ``docs/SECURITY.md`` §6). The verdict/benign split is M1's; the loop only
# decides whether to keep gathering.
_DECISIVE_VERDICTS = frozenset({"malicious", "benign"})


def make_tool_request(
    *, investigation_id: str, iteration: int, tool_name: ToolName, target: str
) -> ToolRequest:
    """Build the concrete request for a proposed tool.

    ``request_id`` is derived from the investigation id and iteration — the model
    proposes only the *tool*, never its identity (T-AI-006), and the id is
    reproducible so traces are deterministic.
    """
    return ToolRequest(
        request_id=f"{investigation_id}-req-{iteration}",
        tool_name=tool_name,
        arguments={"target": target},
    )


def evidence_is_decisive(record: EvidenceRecord) -> bool:
    """True iff one collected record carries a decisive reputation *claim*.

    The verdict match is intentionally exact (lowercase literals): this reads an
    untrusted structured field, and a fuzzy/normalizing match would widen the
    stop surface. A non-canonical value (e.g. "Malicious") is treated as
    non-decisive on purpose — do not "fix" this into a case-insensitive match.
    """
    if record.status is not CollectionStatus.SUCCESS or not record.payload:
        return False
    return record.payload.get(CLAIMED_VERDICT_KEY) in _DECISIVE_VERDICTS


def evidence_is_sufficient(evidence: list[EvidenceRecord]) -> bool:
    """Pure predicate over collected evidence. Reads only the structured
    ``claimed_verdict`` field — never free-text payload notes — so adversarial
    text in a tool response cannot flip the stopping decision (T-TOOL-003)."""
    return any(evidence_is_decisive(record) for record in evidence)


def conclusion_reason(
    evidence: list[EvidenceRecord], *, iteration: int
) -> TerminationReason:
    """The enumerated reason for a non-error conclusion. Deterministic and total:
    sufficiency wins; otherwise hitting the iteration cap; otherwise the model
    chose to stop with nothing further to try."""
    if evidence_is_sufficient(evidence):
        return TerminationReason.SUFFICIENT_EVIDENCE
    if iteration >= MAX_INVESTIGATION_ITERATIONS:
        return TerminationReason.MAX_ITERATIONS
    return TerminationReason.NO_ACTIONABLE_STEP
