"""Domain models and enums. Framework-independent. Pydantic v2.

These types are the shared vocabulary both framework adapters speak. They carry
no orchestration behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class IOCType(str, Enum):
    DOMAIN = "domain"
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    URL = "url"
    SHA256 = "sha256"
    UNKNOWN = "unknown"


class ToolName(str, Enum):
    LOOKUP_DOMAIN = "lookup_domain"
    LOOKUP_IP = "lookup_ip"
    LOOKUP_HASH = "lookup_hash"
    LOOKUP_CVE = "lookup_cve"
    LOOKUP_MITRE = "lookup_mitre"
    SEARCH_KNOWLEDGE = "search_security_knowledge"
    # Sensitive / privileged tool used to exercise approval + unauthorized paths.
    EXPORT_INTEL = "export_intel"


class ToolStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


class InvestigationStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    COLLECTING_EVIDENCE = "collecting_evidence"
    VERIFYING = "verifying"
    WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"
    FAILED = "failed"


class TerminationReason(str, Enum):
    SUFFICIENT_EVIDENCE = "sufficient_evidence"
    MAX_ITERATIONS = "max_iterations"
    RETRY_EXHAUSTED = "retry_exhausted"
    REJECTED_BY_HUMAN = "rejected_by_human"
    POLICY_DENIED = "policy_denied"


class TrustLevel(str, Enum):
    UNTRUSTED = "untrusted"
    NORMALIZED = "normalized"


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


# --------------------------------------------------------------------------- #
# Domain objects
# --------------------------------------------------------------------------- #
class InvestigationInput(BaseModel):
    raw_value: str
    ioc_type: IOCType
    # Objective is fixed application text, never model-writable (T-AI-006).
    objective: str = "Determine whether the IOC is malicious, with evidence."


class ToolRequest(BaseModel):
    request_id: str
    tool_name: ToolName
    arguments: dict[str, str] = Field(default_factory=dict)
    requested_by: str = "investigator"


class ToolResult(BaseModel):
    request_id: str
    tool_name: ToolName
    status: ToolStatus
    # Raw payload is untrusted data (T-TOOL-003); never interpreted as instructions.
    raw_payload: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: int = 0


class Evidence(BaseModel):
    evidence_id: str
    tool_run_id: str
    source: str
    source_reference: str
    collected_at: datetime = Field(default_factory=_utcnow)
    raw_reference: str
    normalized_value: dict[str, object] = Field(default_factory=dict)
    confidence: float = 0.0
    trust_level: TrustLevel = TrustLevel.NORMALIZED


class InvestigationPlan(BaseModel):
    objective: str
    required_evidence: list[str]
    proposed_actions: list[str]
    stop_conditions: list[str]


class VerificationResult(BaseModel):
    sufficient: bool
    contradictions: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class Verdict(BaseModel):
    classification: str  # malicious | suspicious | benign | inconclusive
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)
    contradictory_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    """Unified observable timeline entry. Same schema for both frameworks so
    RESULTS.md comparisons are apples-to-apples. No secrets, no chain-of-thought.
    """

    step: str
    detail: dict[str, object] = Field(default_factory=dict)
    at: datetime = Field(default_factory=_utcnow)
