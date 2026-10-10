"""Integration test: the full threat-intel collection vertical slice.

Exercises the real path end to end — raw observable → ``parse_ioc`` → ``collect``
with the deterministic :class:`MockThreatIntelProvider` → inspectable
:class:`EvidenceRecord`s — across the malicious / benign / unknown / unavailable /
malformed scenarios. No network, no clock, no randomness (the clock is injected).

This proves the slice produces actual, inspectable evidence rather than only
unit-level behaviour, and that every scenario maps to the expected outcome.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from argus.application.collection import (
    CLAIMED_VERDICT_KEY,
    CollectionOutcome,
    collect,
)
from argus.domain.evidence import CollectionStatus, EvidenceKind
from argus.domain.ioc import parse_ioc
from argus.infrastructure.mock_threat_intel import MockThreatIntelProvider

AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.fixture
def providers() -> list[MockThreatIntelProvider]:
    return [MockThreatIntelProvider()]


@pytest.mark.parametrize(
    ("raw", "outcome", "status", "verdict"),
    [
        (
            "203.0.113.66",
            CollectionOutcome.SUCCESS,
            CollectionStatus.SUCCESS,
            "malicious",
        ),
        (
            "malware-c2.example",
            CollectionOutcome.SUCCESS,
            CollectionStatus.SUCCESS,
            "malicious",
        ),
        ("8.8.8.8", CollectionOutcome.SUCCESS, CollectionStatus.SUCCESS, "benign"),
        (
            "cloudflare.com",
            CollectionOutcome.SUCCESS,
            CollectionStatus.SUCCESS,
            "benign",
        ),
        ("198.51.100.23", CollectionOutcome.NO_FINDINGS, CollectionStatus.EMPTY, None),
        (
            "unknown-indicator.example",
            CollectionOutcome.NO_FINDINGS,
            CollectionStatus.EMPTY,
            None,
        ),
        ("192.0.2.200", CollectionOutcome.FAILURE, CollectionStatus.FAILURE, None),
        (
            "malformed.example",
            CollectionOutcome.FAILURE,
            CollectionStatus.FAILURE,
            None,
        ),
    ],
)
def test_scenarios_produce_expected_evidence(
    providers: list[MockThreatIntelProvider],
    raw: str,
    outcome: CollectionOutcome,
    status: CollectionStatus,
    verdict: str | None,
) -> None:
    result = collect(parse_ioc(raw), providers, collected_at=AT)

    assert result.outcome is outcome
    first = result.evidence[0]
    assert first.status is status
    assert first.kind is EvidenceKind.CLAIM  # external source, never a fact
    assert first.provenance.source == "mock-threatintel"
    assert first.subject.raw == raw

    if verdict is not None:
        assert first.payload is not None
        assert first.payload[CLAIMED_VERDICT_KEY] == verdict
        assert first.payload["simulated"] == "true"
    else:
        assert first.payload is None


def test_failure_evidence_carries_error_not_fabricated_payload(
    providers: list[MockThreatIntelProvider],
) -> None:
    result = collect(parse_ioc("192.0.2.200"), providers, collected_at=AT)
    failure = result.evidence[0]
    assert failure.error is not None
    assert failure.payload is None


def test_result_records_which_provider_was_queried(
    providers: list[MockThreatIntelProvider],
) -> None:
    result = collect(parse_ioc("8.8.8.8"), providers, collected_at=AT)
    assert result.providers_queried == ("mock-threatintel",)
    assert result.subject.normalized == "8.8.8.8"
