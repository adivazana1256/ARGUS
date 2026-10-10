"""Unit tests for the investigation lifecycle (M1 Investigation Core).

Covers the state machine, evidence-association invariants, the verdict-free
summary, determinism and serialization round-trips. Providers here are tiny
in-test fakes (pure, offline) so these stay true unit tests; the full wiring over
the real mock provider lives in the integration suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from argus.application.collection import (
    CLAIMED_VERDICT_KEY,
    CollectionOutcome,
    ProviderError,
    ProviderResponse,
    ProviderResponseStatus,
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
from argus.domain.evidence import (
    CollectionStatus,
    EvidenceKind,
    EvidenceRecord,
    Provenance,
)
from argus.domain.ioc import Ioc, IocType, IocValidationError, parse_ioc

AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
ID = "inv-0001"


# --------------------------------------------------------------------------- #
# In-test provider fakes (offline, deterministic).
# --------------------------------------------------------------------------- #


class _FoundProvider:
    name = "fake-found"
    supported_types = frozenset({IocType.IPV4, IocType.DOMAIN})

    def query(self, ioc: Ioc) -> ProviderResponse:
        return ProviderResponse(
            status=ProviderResponseStatus.FOUND,
            records=({CLAIMED_VERDICT_KEY: "malicious", "simulated": "true"},),
            reference="fake://found",
        )


class _EmptyProvider:
    name = "fake-empty"
    supported_types = frozenset({IocType.IPV4, IocType.DOMAIN})

    def query(self, ioc: Ioc) -> ProviderResponse:
        return ProviderResponse(status=ProviderResponseStatus.NOT_FOUND)


class _FailingProvider:
    name = "fake-failing"
    supported_types = frozenset({IocType.IPV4, IocType.DOMAIN})

    def query(self, ioc: Ioc) -> ProviderResponse:
        raise ProviderError("simulated outage")


class _DomainOnlyProvider:
    name = "fake-domain-only"
    supported_types = frozenset({IocType.DOMAIN})

    def query(self, ioc: Ioc) -> ProviderResponse:  # pragma: no cover - never called
        raise ProviderError("should not be queried for ipv4")


# --------------------------------------------------------------------------- #
# Creation + state machine.
# --------------------------------------------------------------------------- #


def test_create_investigation_starts_in_created() -> None:
    inv = create_investigation(parse_ioc("8.8.8.8"), investigation_id=ID, now=AT)
    assert inv.status is InvestigationStatus.CREATED
    assert inv.subject.normalized == "8.8.8.8"
    assert inv.evidence == ()
    assert inv.outcome is None
    assert inv.created_at == AT == inv.updated_at


def test_valid_transition_created_to_collecting() -> None:
    inv = create_investigation(parse_ioc("8.8.8.8"), investigation_id=ID, now=AT)
    moved = inv.transition_to(InvestigationStatus.COLLECTING, now=AT)
    assert moved.status is InvestigationStatus.COLLECTING
    # original snapshot is untouched (frozen, copy-on-transition)
    assert inv.status is InvestigationStatus.CREATED


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (InvestigationStatus.CREATED, InvestigationStatus.COMPLETED),
        (InvestigationStatus.CREATED, InvestigationStatus.FAILED),
        (InvestigationStatus.COLLECTING, InvestigationStatus.CREATED),
        (InvestigationStatus.COMPLETED, InvestigationStatus.COLLECTING),
        (InvestigationStatus.FAILED, InvestigationStatus.COMPLETED),
        (InvestigationStatus.PARTIAL, InvestigationStatus.COMPLETED),
    ],
)
def test_invalid_transitions_are_rejected(
    start: InvestigationStatus, target: InvestigationStatus
) -> None:
    inv = create_investigation(
        parse_ioc("8.8.8.8"), investigation_id=ID, now=AT
    ).model_copy(update={"status": start})
    with pytest.raises(InvalidTransitionError):
        inv.transition_to(target, now=AT)


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        create_investigation(
            parse_ioc("8.8.8.8"),
            investigation_id=ID,
            now=datetime(2026, 1, 2, 3, 4, 5),  # deliberately naive
        )


def test_timestamp_is_normalized_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    aware = datetime(2026, 1, 2, 5, 4, 5, tzinfo=plus_two)
    inv = create_investigation(parse_ioc("8.8.8.8"), investigation_id=ID, now=aware)
    assert inv.created_at == AT  # 05:04 +02:00 == 03:04 UTC
    assert inv.created_at.tzinfo is UTC


@pytest.mark.parametrize("bad_id", ["", "x" * 513])
def test_investigation_id_is_bounded(bad_id: str) -> None:
    with pytest.raises(ValueError, match="investigation_id"):
        create_investigation(parse_ioc("8.8.8.8"), investigation_id=bad_id, now=AT)


# --------------------------------------------------------------------------- #
# End-to-end lifecycle outcomes (fake providers).
# --------------------------------------------------------------------------- #


def test_successful_investigation() -> None:
    inv = run_investigation("8.8.8.8", [_FoundProvider()], investigation_id=ID, now=AT)
    assert inv.status is InvestigationStatus.COMPLETED
    assert inv.outcome is CollectionOutcome.SUCCESS
    assert len(inv.evidence) == 1
    record = inv.evidence[0]
    assert record.kind is EvidenceKind.CLAIM  # a source claim, never an ARGUS fact
    assert record.payload is not None
    assert record.payload[CLAIMED_VERDICT_KEY] == "malicious"


def test_no_findings_investigation_completes_but_is_not_benign() -> None:
    inv = run_investigation("8.8.8.8", [_EmptyProvider()], investigation_id=ID, now=AT)
    assert inv.status is InvestigationStatus.COMPLETED
    assert inv.outcome is CollectionOutcome.NO_FINDINGS
    summary = summarize(inv)
    assert any("not evidence of benignness" in lim for lim in summary.limitations)


def test_partial_collection() -> None:
    inv = run_investigation(
        "8.8.8.8",
        [_FoundProvider(), _FailingProvider()],
        investigation_id=ID,
        now=AT,
    )
    assert inv.status is InvestigationStatus.PARTIAL
    assert inv.outcome is CollectionOutcome.PARTIAL
    summary = summarize(inv)
    assert any("partial" in lim.lower() for lim in summary.limitations)


def test_provider_failure_investigation() -> None:
    inv = run_investigation(
        "8.8.8.8", [_FailingProvider()], investigation_id=ID, now=AT
    )
    assert inv.status is InvestigationStatus.FAILED
    assert inv.outcome is CollectionOutcome.FAILURE
    failure = inv.evidence[0]
    assert failure.status is CollectionStatus.FAILURE
    assert failure.error is not None
    assert failure.payload is None  # failure never carries fabricated data


def test_unsupported_ioc_fails_without_a_capable_provider() -> None:
    # An IPv4 IOC handed only to a domain-only provider: nobody can look.
    inv = run_investigation(
        "8.8.8.8", [_DomainOnlyProvider()], investigation_id=ID, now=AT
    )
    assert inv.status is InvestigationStatus.FAILED
    assert inv.outcome is CollectionOutcome.FAILURE
    assert inv.evidence == ()
    assert inv.providers_queried == ()
    summary = summarize(inv)
    assert any("No configured provider supports" in lim for lim in summary.limitations)


def test_malformed_ioc_opens_no_investigation() -> None:
    with pytest.raises(IocValidationError):
        run_investigation(
            "not a valid ioc", [_FoundProvider()], investigation_id=ID, now=AT
        )


# --------------------------------------------------------------------------- #
# Evidence association invariants.
# --------------------------------------------------------------------------- #


def _claim_for(ioc: Ioc, *, investigation_id: str | None = ID) -> EvidenceRecord:
    return EvidenceRecord(
        kind=EvidenceKind.CLAIM,
        status=CollectionStatus.EMPTY,
        subject=ioc,
        provenance=Provenance(source="fake", collected_at=AT),
        investigation_id=investigation_id,
    )


def test_duplicate_evidence_is_deduped() -> None:
    inv = create_investigation(parse_ioc("8.8.8.8"), investigation_id=ID, now=AT)
    record = _claim_for(inv.subject)
    once = inv.with_evidence([record], now=AT)
    twice = once.with_evidence([record], now=AT)
    assert len(once.evidence) == 1
    assert len(twice.evidence) == 1  # identical content-addressed id, skipped


def test_cross_ioc_evidence_mismatch_is_rejected() -> None:
    inv = create_investigation(parse_ioc("8.8.8.8"), investigation_id=ID, now=AT)
    foreign = _claim_for(parse_ioc("1.1.1.1"))
    with pytest.raises(EvidenceAssociationError, match="subject"):
        inv.with_evidence([foreign], now=AT)


def test_cross_investigation_evidence_is_rejected() -> None:
    inv = create_investigation(parse_ioc("8.8.8.8"), investigation_id=ID, now=AT)
    other = _claim_for(inv.subject, investigation_id="inv-9999")
    with pytest.raises(EvidenceAssociationError, match="different investigation"):
        inv.with_evidence([other], now=AT)


def test_unstamped_evidence_with_matching_subject_is_accepted() -> None:
    inv = create_investigation(parse_ioc("8.8.8.8"), investigation_id=ID, now=AT)
    unstamped = _claim_for(inv.subject, investigation_id=None)
    assert len(inv.with_evidence([unstamped], now=AT).evidence) == 1


def test_association_preserves_provenance_and_object_identity() -> None:
    inv = run_investigation("8.8.8.8", [_FoundProvider()], investigation_id=ID, now=AT)
    record = inv.evidence[0]
    # provenance.source is the trusted provider name, carried through unchanged
    assert record.provenance.source == "fake-found"
    assert record.provenance.source_reference == "fake://found"
    assert record.provenance.collected_at == AT


# --------------------------------------------------------------------------- #
# Summary.
# --------------------------------------------------------------------------- #


def test_summary_is_verdict_free() -> None:
    inv = run_investigation("8.8.8.8", [_FoundProvider()], investigation_id=ID, now=AT)
    summary = summarize(inv)
    assert summary.investigation_id == ID
    assert summary.ioc_type == "ipv4"
    assert summary.normalized_value == "8.8.8.8"
    assert summary.evidence_count == 1
    assert summary.evidence_ids == (inv.evidence[0].evidence_id,)
    # the claimed verdict is NOT surfaced as an ARGUS conclusion anywhere in summary
    flat = summary.model_dump_json()
    assert "malicious" not in flat
    assert any("source claims" in lim for lim in summary.limitations)


# --------------------------------------------------------------------------- #
# Determinism + serialization.
# --------------------------------------------------------------------------- #


def test_repeated_execution_is_deterministic() -> None:
    first = run_investigation(
        "8.8.8.8", [_FoundProvider()], investigation_id=ID, now=AT
    )
    second = run_investigation(
        "8.8.8.8", [_FoundProvider()], investigation_id=ID, now=AT
    )
    assert first == second
    assert summarize(first) == summarize(second)


def test_investigation_serialization_round_trip() -> None:
    inv = run_investigation(
        "cloudflare.com", [_FoundProvider()], investigation_id=ID, now=AT
    )
    restored = Investigation.model_validate(inv.model_dump())
    assert restored == inv
    # evidence_id is recomputed on load and must still match (tamper-evident)
    assert restored.evidence[0].evidence_id == inv.evidence[0].evidence_id


def test_summary_serialization_round_trip() -> None:
    inv = run_investigation("8.8.8.8", [_EmptyProvider()], investigation_id=ID, now=AT)
    summary = summarize(inv)
    restored = InvestigationSummary.model_validate(summary.model_dump())
    assert restored == summary
