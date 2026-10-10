"""Tests for the deterministic mock threat-intel provider.

Scope: the provider adapter in isolation — fixture correctness across the
malicious / benign / unknown / unavailable / malformed scenarios, the simulated
labelling, response-schema enforcement at the boundary, and determinism. The
orchestration that consumes these responses is owned by ``test_collection.py``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from argus.application.collection import (
    CLAIMED_VERDICT_KEY,
    ProviderError,
    ProviderResponse,
    ProviderResponseStatus,
)
from argus.domain.ioc import IocType, parse_ioc
from argus.infrastructure.mock_threat_intel import (
    PROVIDER_NAME,
    MockThreatIntelProvider,
)

PROVIDER = MockThreatIntelProvider()


def _query(raw: str) -> ProviderResponse:
    return PROVIDER.query(parse_ioc(raw))


# --------------------------------------------------------------------------- #
# Contract / capability.
# --------------------------------------------------------------------------- #


def test_declares_name_and_supported_types() -> None:
    assert PROVIDER.name == PROVIDER_NAME
    assert PROVIDER.supported_types == frozenset({IocType.IPV4, IocType.DOMAIN})


def test_name_is_clearly_simulated() -> None:
    # The source attribution itself must not read like a real provider.
    assert "mock" in PROVIDER.name


# --------------------------------------------------------------------------- #
# Fixture scenarios.
# --------------------------------------------------------------------------- #


def test_malicious_ip_is_found_with_verdict() -> None:
    response = _query("203.0.113.66")
    assert response.status is ProviderResponseStatus.FOUND
    assert response.records[0][CLAIMED_VERDICT_KEY] == "malicious"


def test_benign_ip_is_found_with_verdict() -> None:
    response = _query("8.8.8.8")
    assert response.status is ProviderResponseStatus.FOUND
    assert response.records[0][CLAIMED_VERDICT_KEY] == "benign"


def test_malicious_domain_can_carry_multiple_records() -> None:
    response = _query("malware-c2.example")
    verdicts = [r[CLAIMED_VERDICT_KEY] for r in response.records]
    assert verdicts == ["malicious", "suspicious"]


def test_unknown_indicator_is_not_found() -> None:
    assert _query("198.51.100.23").status is ProviderResponseStatus.NOT_FOUND


def test_indicator_with_no_fixture_is_not_found_not_fabricated() -> None:
    # A source with no data answers NOT_FOUND — never an invented benign result.
    response = _query("1.2.3.4")
    assert response.status is ProviderResponseStatus.NOT_FOUND
    assert response.records == ()


def test_unavailable_provider_outage() -> None:
    assert _query("192.0.2.200").status is ProviderResponseStatus.UNAVAILABLE


# --------------------------------------------------------------------------- #
# Simulated labelling — every finding is unambiguously fake.
# --------------------------------------------------------------------------- #


def test_every_found_record_is_marked_simulated() -> None:
    for raw in ("203.0.113.66", "8.8.8.8", "cloudflare.com", "malware-c2.example"):
        response = _query(raw)
        for record in response.records:
            assert record["simulated"] == "true"
            assert record["provider_kind"] == "mock"


# --------------------------------------------------------------------------- #
# Schema enforcement at the boundary.
# --------------------------------------------------------------------------- #


def test_malformed_fixture_is_rejected_by_schema() -> None:
    # The provider parses its own stored payload; a bad one fails validation here,
    # at the real boundary, rather than producing an unchecked response object.
    with pytest.raises(ValidationError):
        _query("malformed.example")


def test_response_rejects_too_many_records() -> None:
    with pytest.raises(ValidationError):
        ProviderResponse(
            status=ProviderResponseStatus.FOUND,
            records=tuple({"i": str(i)} for i in range(17)),
        )


def test_response_rejects_oversized_reference() -> None:
    with pytest.raises(ValidationError):
        ProviderResponse(status=ProviderResponseStatus.NOT_FOUND, reference="x" * 513)


def test_unsupported_type_is_refused_explicitly() -> None:
    # Hand the provider an IOC whose type it does not list as supported.
    class _FakeIoc:
        ioc_type = "sha256"
        normalized = "deadbeef"

    with pytest.raises(ProviderError):
        PROVIDER.query(_FakeIoc())  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Determinism.
# --------------------------------------------------------------------------- #


def test_repeated_queries_are_identical() -> None:
    a = _query("203.0.113.66")
    b = _query("203.0.113.66")
    assert a.model_dump() == b.model_dump()
