"""Domain rules: deterministic domain TRUTHS only.

Every function here answers a domain question ("what type is this IOC?", "does
the collected evidence decide the case?", "what verdict does this evidence
imply?"). None of them decide *when to loop*, *when to retry*, *when to pause* or
*how to transition* — that is orchestration and belongs to each framework
adapter. Keeping these answers shared is what makes the comparison fair: neither
framework can "win" by judging evidence differently.
"""

from __future__ import annotations

import re

from .models import (
    Evidence,
    InvestigationInput,
    InvestigationPlan,
    IOCType,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
    TrustLevel,
    Verdict,
    VerificationResult,
)
from .state import InvestigationState

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9-]+\.)+[a-z]{2,}$", re.IGNORECASE)
_IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$", re.IGNORECASE)


def detect_ioc_type(raw: str) -> IOCType:
    raw = raw.strip()
    if _SHA256_RE.match(raw):
        return IOCType.SHA256
    if _IPV4_RE.match(raw):
        return IOCType.IPV4
    if raw.startswith(("http://", "https://")):
        return IOCType.URL
    if _DOMAIN_RE.match(raw):
        return IOCType.DOMAIN
    return IOCType.UNKNOWN


def build_plan(inv_input: InvestigationInput) -> InvestigationPlan:
    return InvestigationPlan(
        objective=inv_input.objective,
        required_evidence=["reputation of the IOC from threat intelligence"],
        proposed_actions=["enrich IOC via threat-intelligence lookup"],
        stop_conditions=[
            "decisive reputation evidence collected",
            "maximum investigation iterations reached",
            "tool retries exhausted",
            "human rejects a required approval",
        ],
    )


def make_tool_request(state: InvestigationState, tool_name: ToolName) -> ToolRequest:
    """Build the ToolRequest the investigator proposes. Deterministic id keyed to
    iteration so traces are reproducible. Proposing is a domain act; authorizing
    it is ToolPolicy, and executing/looping is framework orchestration.
    """
    return ToolRequest(
        request_id=f"{state.investigation_id}-req-{state.iteration}",
        tool_name=tool_name,
        arguments={"target": state.input.raw_value},
    )


def normalize_evidence(result: ToolResult) -> Evidence:
    """Convert an untrusted raw tool payload into normalized Evidence. Only known
    structured fields are lifted; free-text notes stay as data, never executed.
    """
    rep = str(result.raw_payload.get("reputation", "unknown"))
    score = float(result.raw_payload.get("score", 0.0) or 0.0)
    return Evidence(
        evidence_id=f"ev-{result.request_id}",
        tool_run_id=result.request_id,
        source=result.tool_name.value,
        source_reference=result.request_id,
        raw_reference=str(result.raw_payload.get("note", "")),
        normalized_value={"reputation": rep, "score": score},
        confidence=score,
        trust_level=TrustLevel.NORMALIZED,
    )


def _decisive(ev: Evidence) -> bool:
    rep = ev.normalized_value.get("reputation")
    score = float(ev.normalized_value.get("score", 0.0) or 0.0)
    return rep in {"malicious", "clean"} and score >= 0.5


def evidence_sufficient(state: InvestigationState) -> bool:
    """Pure predicate on collected evidence. The adapter decides what to DO with
    this answer (loop vs. stop); the answer itself is identical for both.
    """
    return any(_decisive(ev) for ev in state.evidence)


def verify_evidence(state: InvestigationState) -> VerificationResult:
    sufficient = evidence_sufficient(state)
    missing = [] if sufficient else ["decisive reputation evidence"]
    return VerificationResult(
        sufficient=sufficient,
        missing_evidence=missing,
    )


def synthesize_verdict(state: InvestigationState) -> Verdict:
    decisive = [ev for ev in state.evidence if _decisive(ev)]
    evidence_ids = [ev.evidence_id for ev in state.evidence]
    limitations: list[str] = []
    if not decisive:
        limitations.append("no decisive evidence collected within bounds")
        return Verdict(
            classification="inconclusive",
            confidence=0.2,
            evidence_ids=evidence_ids,
            limitations=limitations,
        )
    malicious = [ev for ev in decisive if ev.normalized_value.get("reputation") == "malicious"]
    if malicious:
        conf = max(float(ev.normalized_value.get("score", 0.0)) for ev in malicious)
        return Verdict(
            classification="malicious",
            confidence=conf,
            evidence_ids=evidence_ids,
            limitations=limitations,
        )
    conf = max(float(ev.normalized_value.get("score", 0.0)) for ev in decisive)
    return Verdict(
        classification="benign",
        confidence=conf,
        evidence_ids=evidence_ids,
        limitations=limitations,
    )
