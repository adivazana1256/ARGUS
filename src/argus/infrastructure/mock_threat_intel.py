"""Deterministic mock threat-intelligence provider (M1 Slice 4).

An offline :class:`ThreatIntelProvider` adapter that serves fixed, in-memory
fixtures. It exists so the collection pipeline can produce real, inspectable
evidence from realistic threat-intel scenarios without any network access, paid
API, or non-determinism. Infrastructure layer: it is the swappable adapter slot a
real VirusTotal/OTX adapter would later occupy (``docs/ARCHITECTURE.md`` §8).

**All data here is SIMULATED.** The fixtures are invented for testing. They are
not real-world threat intelligence and must never be presented as verified
reputation. The provider name and a ``simulated`` marker on every finding keep
that explicit end to end; the collection layer records these as untrusted CLAIMs,
never as ARGUS-derived facts or verdicts.

Determinism: the response for a given IOC is a pure lookup keyed on the IOC's
normalized form. No clock, no randomness, no network, no I/O.
"""

from __future__ import annotations

from argus.application.collection import (
    CLAIMED_VERDICT_KEY,
    ProviderError,
    ProviderResponse,
    ProviderResponseStatus,
)
from argus.domain.ioc import Ioc, IocType

PROVIDER_NAME = "mock-threatintel"

# Marker stamped into every FOUND record so stored evidence is unambiguously
# simulated. It is a payload field (a claim about the claim), not a verdict.
_SIMULATED = {"simulated": "true", "provider_kind": "mock"}


def _found(verdict: str, **extra: str) -> dict[str, str]:
    """Build one simulated finding record claiming ``verdict``."""
    return {CLAIMED_VERDICT_KEY: verdict, **_SIMULATED, **extra}


# Fixture table keyed on the IOC's normalized form. Each value is either a
# ready-to-serve ProviderResponse, or a raw dict that intentionally violates the
# response schema (the "malformed" scenario) to exercise the boundary guard.
#
# Scenarios covered (docs/EVALUATION.md §3 categories):
#   malicious / benign  -> FOUND with a claimed_verdict
#   unknown             -> NOT_FOUND
#   unavailable         -> UNAVAILABLE (simulated outage)
#   malformed           -> a response that fails schema validation at the boundary
_FIXTURES: dict[str, ProviderResponse] = {
    # --- malicious claims ---
    "203.0.113.66": ProviderResponse(
        status=ProviderResponseStatus.FOUND,
        records=(
            _found(
                "malicious",
                category="c2",
                threat="simulated-botnet-panel",
                last_seen="2026-01-01",
            ),
        ),
        reference="mock://ip/203.0.113.66",
    ),
    "malware-c2.example": ProviderResponse(
        status=ProviderResponseStatus.FOUND,
        records=(
            _found("malicious", category="malware_distribution"),
            _found("suspicious", category="newly_registered"),
        ),
        reference="mock://domain/malware-c2.example",
    ),
    # --- benign claims ---
    "8.8.8.8": ProviderResponse(
        status=ProviderResponseStatus.FOUND,
        records=(_found("benign", category="public_dns"),),
        reference="mock://ip/8.8.8.8",
    ),
    "cloudflare.com": ProviderResponse(
        status=ProviderResponseStatus.FOUND,
        records=(_found("benign", category="cdn"),),
        reference="mock://domain/cloudflare.com",
    ),
    # --- unknown: provider ran, has nothing ---
    "198.51.100.23": ProviderResponse(status=ProviderResponseStatus.NOT_FOUND),
    "unknown-indicator.example": ProviderResponse(
        status=ProviderResponseStatus.NOT_FOUND
    ),
    # --- unavailable: simulated provider outage ---
    "192.0.2.200": ProviderResponse(status=ProviderResponseStatus.UNAVAILABLE),
}

# Normalized IOCs that trigger a malformed (schema-violating) response, served as
# a raw payload the provider tries — and fails — to parse. Kept separate from the
# validated table above precisely because they cannot be a ProviderResponse.
_MALFORMED: dict[str, dict[str, object]] = {
    # `status` is not a member of ProviderResponseStatus.
    "malformed.example": {"status": "garbage", "records": []},
}


class MockThreatIntelProvider:
    """Offline threat-intel adapter backed by fixed fixtures.

    Satisfies the :class:`~argus.application.collection.ThreatIntelProvider`
    protocol. Supports both IOC types ARGUS can classify today. Any IOC with no
    fixture is reported as ``NOT_FOUND`` — the honest answer for a source that
    simply has no data, never a fabricated benign result.
    """

    name = PROVIDER_NAME
    supported_types = frozenset({IocType.IPV4, IocType.DOMAIN})

    def query(self, ioc: Ioc) -> ProviderResponse:
        if ioc.ioc_type not in {t.value for t in self.supported_types}:
            # Defensive: the orchestrator pre-filters, but a provider must still
            # refuse an unsupported type explicitly rather than guess.
            raise ProviderError(f"unsupported IOC type: {ioc.ioc_type}")

        key = ioc.normalized
        if key in _MALFORMED:
            # Parse the deliberately-bad payload here so the schema guard runs at
            # the real provider boundary; this raises and the orchestrator maps it
            # to a FAILURE record.
            return ProviderResponse(**_MALFORMED[key])  # type: ignore[arg-type]
        return _FIXTURES.get(
            key, ProviderResponse(status=ProviderResponseStatus.NOT_FOUND)
        )
