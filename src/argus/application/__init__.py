"""Application layer: use-cases and ports (interfaces) over the domain.

Imports `domain`; must not import `api` or `infrastructure` (M0 spec §1.1).
Hosts the threat-intel collection use-case and its provider port (M1 Slice 4).
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

__all__ = [
    "CLAIMED_VERDICT_KEY",
    "CollectionOutcome",
    "CollectionResult",
    "ProviderError",
    "ProviderResponse",
    "ProviderResponseStatus",
    "ThreatIntelProvider",
    "collect",
]
