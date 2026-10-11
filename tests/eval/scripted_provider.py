"""Deterministic scripted threat-intel provider for agent evals.

Satisfies the production :class:`~argus.application.collection.ThreatIntelProvider`
contract but serves a *scripted sequence* of responses so stateful scenarios
(fail-then-recover, insufficient-then-decisive) are explicit and reproducible
rather than hidden in global counters. Offline, no clock, no randomness — call N
returns script entry N; the last entry repeats once the script is exhausted.
"""

from __future__ import annotations

from argus.application.collection import (
    CLAIMED_VERDICT_KEY,
    ProviderError,
    ProviderResponse,
    ProviderResponseStatus,
)
from argus.domain.ioc import Ioc, IocType

# One scripted outcome is either a ready response or an error to raise.
ScriptEntry = ProviderResponse | ProviderError


class ScriptedProvider:
    """A provider whose per-call behavior is an explicit script, reset per test."""

    name = "scripted-threatintel"
    supported_types = frozenset({IocType.IPV4, IocType.DOMAIN})

    def __init__(self, script: list[ScriptEntry]) -> None:
        if not script:
            raise ValueError("script must have at least one entry")
        self._script = script
        self._index = 0

    def query(self, ioc: Ioc) -> ProviderResponse:
        entry = self._script[min(self._index, len(self._script) - 1)]
        self._index += 1
        if isinstance(entry, ProviderError):
            raise entry
        return entry


def found(verdict: str, **extra: str) -> ProviderResponse:
    """A FOUND response claiming ``verdict`` (simulated, untrusted)."""
    record = {CLAIMED_VERDICT_KEY: verdict, "simulated": "true", **extra}
    return ProviderResponse(
        status=ProviderResponseStatus.FOUND,
        records=(record,),
        reference="scripted://finding",
    )


def not_found() -> ProviderResponse:
    """Provider ran, has nothing — absence, never a benign claim."""
    return ProviderResponse(status=ProviderResponseStatus.NOT_FOUND)


def unavailable() -> ProviderResponse:
    """Simulated provider outage → a FAILURE collection → a bounded retry."""
    return ProviderResponse(status=ProviderResponseStatus.UNAVAILABLE)
