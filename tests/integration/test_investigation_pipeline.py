"""Integration test: the full investigation lifecycle over the mock provider.

Exercises the real end-to-end path — raw observable -> ``run_investigation`` with
the offline :class:`MockThreatIntelProvider` -> lifecycle transitions -> associated
:class:`EvidenceRecord`s -> deterministic :class:`InvestigationSummary` — across
every collection scenario. No network, no clock, no randomness (the clock and id
are injected). This proves the slice produces an actual, inspectable investigation
rather than only unit-level behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from argus.application.collection import (
    CollectionOutcome,
    ProviderError,
    ProviderResponse,
    ThreatIntelProvider,
)
from argus.application.investigation import (
    InvestigationStatus,
    run_investigation,
    summarize,
)
from argus.domain.evidence import CollectionStatus
from argus.domain.ioc import Ioc, IocType, IocValidationError
from argus.infrastructure.mock_threat_intel import MockThreatIntelProvider

AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
ID = "inv-integration-0001"


class _AlwaysFailingProvider:
    """A second provider that always fails — used to force a PARTIAL outcome."""

    name = "always-failing"
    supported_types = frozenset({IocType.IPV4, IocType.DOMAIN})

    def query(self, ioc: Ioc) -> ProviderResponse:
        raise ProviderError("simulated outage")


@pytest.fixture
def providers() -> list[MockThreatIntelProvider]:
    return [MockThreatIntelProvider()]


@pytest.mark.parametrize(
    ("raw", "status", "outcome"),
    [
        ("203.0.113.66", InvestigationStatus.COMPLETED, CollectionOutcome.SUCCESS),
        (
            "malware-c2.example",
            InvestigationStatus.COMPLETED,
            CollectionOutcome.SUCCESS,
        ),
        ("8.8.8.8", InvestigationStatus.COMPLETED, CollectionOutcome.SUCCESS),
        (
            "198.51.100.23",
            InvestigationStatus.COMPLETED,
            CollectionOutcome.NO_FINDINGS,
        ),
        ("192.0.2.200", InvestigationStatus.FAILED, CollectionOutcome.FAILURE),
        ("malformed.example", InvestigationStatus.FAILED, CollectionOutcome.FAILURE),
    ],
)
def test_scenarios_drive_expected_lifecycle(
    providers: list[MockThreatIntelProvider],
    raw: str,
    status: InvestigationStatus,
    outcome: CollectionOutcome,
) -> None:
    inv = run_investigation(raw, providers, investigation_id=ID, now=AT)

    assert inv.status is status
    assert inv.outcome is outcome
    assert inv.providers_queried == ("mock-threatintel",)
    # every associated record is about this exact IOC and carries this id
    for record in inv.evidence:
        assert record.subject.normalized == inv.subject.normalized
        assert record.investigation_id == ID


def test_malformed_ioc_opens_no_investigation(
    providers: list[MockThreatIntelProvider],
) -> None:
    with pytest.raises(IocValidationError):
        run_investigation("not an ioc!!", providers, investigation_id=ID, now=AT)


def test_partial_when_one_provider_fails(
    providers: list[MockThreatIntelProvider],
) -> None:
    both: list[ThreatIntelProvider] = [*providers, _AlwaysFailingProvider()]
    inv = run_investigation("8.8.8.8", both, investigation_id=ID, now=AT)

    assert inv.status is InvestigationStatus.PARTIAL
    assert inv.outcome is CollectionOutcome.PARTIAL
    statuses = {record.status for record in inv.evidence}
    assert CollectionStatus.FAILURE in statuses  # the failing provider's record
    assert CollectionStatus.SUCCESS in statuses  # the mock's benign claim
    summary = summarize(inv)
    assert any("partial" in lim.lower() for lim in summary.limitations)


def test_failure_evidence_is_not_fabricated(
    providers: list[MockThreatIntelProvider],
) -> None:
    inv = run_investigation("192.0.2.200", providers, investigation_id=ID, now=AT)
    failure = inv.evidence[0]
    assert failure.status is CollectionStatus.FAILURE
    assert failure.error is not None
    assert failure.payload is None


def test_repeated_execution_is_deterministic(
    providers: list[MockThreatIntelProvider],
) -> None:
    first = run_investigation("203.0.113.66", providers, investigation_id=ID, now=AT)
    second = run_investigation(
        "203.0.113.66", [MockThreatIntelProvider()], investigation_id=ID, now=AT
    )
    assert first == second
    assert summarize(first) == summarize(second)
