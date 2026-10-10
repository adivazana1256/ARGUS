"""Application layer: use-cases and ports (interfaces) over the domain.

Imports `domain`; must not import `api` or `infrastructure` (M0 spec §1.1).
Hosts the threat-intel collection use-case and its provider port (M1 Slice 4)
and the investigation lifecycle use-case (M1 Investigation Core).
"""

from argus.application.collection import (
    CLAIMED_VERDICT_KEY,
    CollectionOutcome,
    CollectionResult,
    ProviderError,
    ProviderResponse,
    ProviderResponseStatus,
    ThreatIntelProvider,
    collect,
)
from argus.application.investigation import (
    EvidenceAssociationError,
    InvalidTransitionError,
    Investigation,
    InvestigationStatus,
    InvestigationSummary,
    create_investigation,
    run_investigation,
    summarize,
)

__all__ = [
    "CLAIMED_VERDICT_KEY",
    "CollectionOutcome",
    "CollectionResult",
    "EvidenceAssociationError",
    "Investigation",
    "InvestigationStatus",
    "InvestigationSummary",
    "InvalidTransitionError",
    "ProviderError",
    "ProviderResponse",
    "ProviderResponseStatus",
    "ThreatIntelProvider",
    "collect",
    "create_investigation",
    "run_investigation",
    "summarize",
]
