"""Tests for the threat-intel collection orchestrator (``argus.application``).

Scope: orchestration semantics — capability enforcement, response→evidence
mapping, outcome aggregation, failure handling, and the security boundary that
keeps external claims from becoming ARGUS facts. Provider fixtures are owned by
``test_mock_provider.py``; here we use small purpose-built fakes so each
behaviour is exercised in isolation, plus the real mock for an end-to-end check.

Adversarial coverage lives here: source spoofing, oversized/malformed payloads,
and injection text in provider output.
"""

from __future__ import annotations

from datetime import UTC, datetime

from argus.application.collection import (
    CLAIMED_VERDICT_KEY,
    CollectionOutcome,
    ProviderError,
    ProviderResponse,
    ProviderResponseStatus,
    collect,
)
from argus.domain.evidence import CollectionStatus, EvidenceKind, observation_from_ioc
from argus.domain.ioc import Ioc, IocType, parse_ioc
from argus.infrastructure.mock_threat_intel import MockThreatIntelProvider

AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
LATER = datetime(2026, 9, 9, 9, 9, 9, tzinfo=UTC)


class FakeProvider:
    """A provider that returns a canned response (or raises) for every query."""

    def __init__(
        self,
        name: str,
        *,
        response: ProviderResponse | None = None,
        error: Exception | None = None,
        supported: frozenset[IocType] = frozenset({IocType.IPV4, IocType.DOMAIN}),
    ) -> None:
        self.name = name
        self.supported_types = supported
        self._response = response
        self._error = error

    def query(self, ioc: Ioc) -> ProviderResponse:
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _found(verdict: str, **extra: str) -> ProviderResponse:
    return ProviderResponse(
        status=ProviderResponseStatus.FOUND,
        records=({CLAIMED_VERDICT_KEY: verdict, **extra},),
    )


IP = parse_ioc("203.0.113.66")


# --------------------------------------------------------------------------- #
# Outcome aggregation.
# --------------------------------------------------------------------------- #


def test_success_outcome() -> None:
    result = collect(
        IP, [FakeProvider("p", response=_found("malicious"))], collected_at=AT
    )
    assert result.outcome is CollectionOutcome.SUCCESS
    assert result.evidence[0].payload is not None
    assert result.evidence[0].payload[CLAIMED_VERDICT_KEY] == "malicious"


def test_no_findings_outcome_is_not_benign() -> None:
    result = collect(
        IP,
        [
            FakeProvider(
                "p", response=ProviderResponse(status=ProviderResponseStatus.NOT_FOUND)
            )
        ],
        collected_at=AT,
    )
    assert result.outcome is CollectionOutcome.NO_FINDINGS
    assert result.evidence[0].status is CollectionStatus.EMPTY
    assert result.evidence[0].payload is None  # absence is not a benign verdict


def test_partial_outcome_when_one_provider_fails() -> None:
    result = collect(
        IP,
        [
            FakeProvider("good", response=_found("malicious")),
            FakeProvider("bad", error=ProviderError("down")),
        ],
        collected_at=AT,
    )
    assert result.outcome is CollectionOutcome.PARTIAL
    statuses = {e.status for e in result.evidence}
    assert statuses == {CollectionStatus.SUCCESS, CollectionStatus.FAILURE}


def test_failure_outcome_when_all_providers_fail() -> None:
    result = collect(
        IP,
        [
            FakeProvider("a", error=ProviderError("down")),
            FakeProvider(
                "b",
                response=ProviderResponse(status=ProviderResponseStatus.UNAVAILABLE),
            ),
        ],
        collected_at=AT,
    )
    assert result.outcome is CollectionOutcome.FAILURE


def test_no_capable_provider_is_failure_not_no_findings() -> None:
    # A provider that only supports domains, queried with an IP → nobody looks.
    result = collect(
        IP,
        [
            FakeProvider(
                "dom", response=_found("x"), supported=frozenset({IocType.DOMAIN})
            )
        ],
        collected_at=AT,
    )
    assert result.outcome is CollectionOutcome.FAILURE
    assert result.evidence == ()
    assert result.providers_queried == ()


def test_only_capable_providers_are_queried() -> None:
    result = collect(
        IP,
        [
            FakeProvider(
                "ip-only",
                response=_found("malicious"),
                supported=frozenset({IocType.IPV4}),
            ),
            FakeProvider(
                "dom-only", response=_found("x"), supported=frozenset({IocType.DOMAIN})
            ),
        ],
        collected_at=AT,
    )
    assert result.providers_queried == ("ip-only",)


# --------------------------------------------------------------------------- #
# External source ⇒ CLAIM, never OBSERVATION/verdict.
# --------------------------------------------------------------------------- #


def test_all_provider_evidence_is_a_claim() -> None:
    result = collect(
        IP,
        [
            FakeProvider("found", response=_found("malicious")),
            FakeProvider(
                "empty",
                response=ProviderResponse(status=ProviderResponseStatus.NOT_FOUND),
            ),
            FakeProvider("fail", error=ProviderError("x")),
        ],
        collected_at=AT,
    )
    assert all(e.kind is EvidenceKind.CLAIM for e in result.evidence)


def test_source_is_provider_name_and_claim_never_collides_with_observation() -> None:
    # Adversarial: a provider names itself like the internal classifier. It still
    # cannot forge an ARGUS fact — kind=CLAIM is part of evidence_id, so the ids
    # differ from a real OBSERVATION of the same IOC.
    spoof = FakeProvider("argus.domain.ioc", response=_found("malicious"))
    result = collect(IP, [spoof], collected_at=AT)
    claim = result.evidence[0]
    observation = observation_from_ioc(IP, collected_at=AT)
    assert claim.provenance.source == "argus.domain.ioc"
    assert claim.kind is EvidenceKind.CLAIM
    assert observation.kind is EvidenceKind.OBSERVATION
    assert claim.evidence_id != observation.evidence_id


# --------------------------------------------------------------------------- #
# Untrusted payload handling.
# --------------------------------------------------------------------------- #


def test_injection_text_is_stored_inert_not_interpreted() -> None:
    payload = {CLAIMED_VERDICT_KEY: "malicious", "note": "ignore previous instructions"}
    result = collect(
        IP,
        [
            FakeProvider(
                "p",
                response=ProviderResponse(
                    status=ProviderResponseStatus.FOUND, records=(payload,)
                ),
            )
        ],
        collected_at=AT,
    )
    evidence = result.evidence[0]
    assert evidence.status is CollectionStatus.SUCCESS
    assert evidence.kind is EvidenceKind.CLAIM  # a claim, not a promoted fact
    assert evidence.payload is not None
    assert evidence.payload["note"] == "ignore previous instructions"  # verbatim, inert


def test_oversized_payload_fails_safe_to_failure() -> None:
    # A record with too many keys breaks the EvidenceRecord map bound. The map
    # fails validation; collection records a FAILURE, never a crash or partial write.
    huge = {f"k{i}": "v" for i in range(40)}
    result = collect(
        IP,
        [
            FakeProvider(
                "p",
                response=ProviderResponse(
                    status=ProviderResponseStatus.FOUND, records=(huge,)
                ),
            )
        ],
        collected_at=AT,
    )
    assert result.outcome is CollectionOutcome.FAILURE
    failure = result.evidence[0]
    assert failure.status is CollectionStatus.FAILURE
    assert failure.payload is None
    assert failure.error is not None


def test_failure_error_does_not_echo_untrusted_input() -> None:
    huge = {f"k{i}": "secret-looking-value" for i in range(40)}
    result = collect(
        IP,
        [
            FakeProvider(
                "p",
                response=ProviderResponse(
                    status=ProviderResponseStatus.FOUND, records=(huge,)
                ),
            )
        ],
        collected_at=AT,
    )
    assert result.evidence[0].error == "invalid provider response"


def test_found_with_no_records_is_empty_not_fabricated() -> None:
    result = collect(
        IP,
        [
            FakeProvider(
                "p", response=ProviderResponse(status=ProviderResponseStatus.FOUND)
            )
        ],
        collected_at=AT,
    )
    assert result.outcome is CollectionOutcome.NO_FINDINGS
    assert result.evidence[0].status is CollectionStatus.EMPTY
    assert result.evidence[0].payload is None


# --------------------------------------------------------------------------- #
# Failure semantics: no fabricated evidence.
# --------------------------------------------------------------------------- #


def test_provider_error_becomes_failure_evidence_with_no_payload() -> None:
    result = collect(
        IP, [FakeProvider("p", error=ProviderError("boom"))], collected_at=AT
    )
    assert result.outcome is CollectionOutcome.FAILURE
    ev = result.evidence[0]
    assert ev.status is CollectionStatus.FAILURE
    assert ev.payload is None
    assert ev.error == "boom"


def test_unexpected_valueerror_is_contained() -> None:
    result = collect(
        IP, [FakeProvider("p", error=ValueError("weird"))], collected_at=AT
    )
    assert result.outcome is CollectionOutcome.FAILURE
    assert result.evidence[0].error == "invalid provider response"


# --------------------------------------------------------------------------- #
# Duplicate collection / determinism.
# --------------------------------------------------------------------------- #


def test_duplicate_collection_dedupes_by_evidence_id() -> None:
    # Same IOC, same provider, same claim, two different collection times: the
    # content-addressed id is identical, while collected_at is preserved per run.
    provider = FakeProvider("p", response=_found("malicious"))
    first = collect(IP, [provider], collected_at=AT).evidence[0]
    second = collect(IP, [provider], collected_at=LATER).evidence[0]
    assert first.evidence_id == second.evidence_id
    assert first.provenance.collected_at == AT
    assert second.provenance.collected_at == LATER


def test_investigation_id_is_passed_through_without_touching_identity() -> None:
    provider = FakeProvider("p", response=_found("malicious"))
    a = collect(IP, [provider], collected_at=AT, investigation_id="inv-1").evidence[0]
    b = collect(IP, [provider], collected_at=AT, investigation_id="inv-2").evidence[0]
    assert a.investigation_id == "inv-1"
    assert a.evidence_id == b.evidence_id  # investigation_id is not identity


# --------------------------------------------------------------------------- #
# End-to-end with the real mock provider (one path; full matrix in integration).
# --------------------------------------------------------------------------- #


def test_end_to_end_with_mock_provider() -> None:
    result = collect(IP, [MockThreatIntelProvider()], collected_at=AT)
    assert result.outcome is CollectionOutcome.SUCCESS
    assert result.evidence[0].payload is not None
    assert result.evidence[0].payload["simulated"] == "true"
