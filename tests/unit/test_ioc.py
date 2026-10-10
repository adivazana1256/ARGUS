"""Tests for the typed IOC entity layer + dispatch (``argus.domain.ioc``).

Scope: the *dispatch* boundary and the type tag introduced by M1 Slice 2 only.
Per-type IPv4 semantics (scope, normalization, the full invalid/boundary tables)
are owned and exercised by ``test_ipv4.py`` and are not re-tested here — these
cases assert routing, self-description and explicit failure for unsupported
input (cyber-domain-review; ``docs/EVALUATION.md`` §4).
"""

from __future__ import annotations

import pytest

from argus.domain.ioc import (
    IocType,
    IocValidationError,
    parse_ioc,
)
from argus.domain.ipv4 import Ipv4Ioc, parse_ipv4

# --------------------------------------------------------------------------- #
# Dispatch: a valid IPv4 routes to the IPv4 type without duplicating its logic.
# --------------------------------------------------------------------------- #


def test_valid_ipv4_dispatches_to_ipv4_entity() -> None:
    ioc = parse_ioc("8.8.8.8")
    assert isinstance(ioc, Ipv4Ioc)
    # StrEnum member equals its string value at runtime; compare via .value so the
    # strict type checker sees overlapping Literal/str operands.
    assert ioc.ioc_type == IocType.IPV4.value


def test_dispatch_matches_direct_ipv4_parse() -> None:
    # parse_ioc delegates to parse_ipv4 — same classification, no reimplementation.
    assert parse_ioc("8.8.8.8") == parse_ipv4("8.8.8.8")
    actionable = parse_ioc("10.0.0.5")
    assert actionable.scope is parse_ipv4("10.0.0.5").scope
    assert actionable.externally_actionable is False


# --------------------------------------------------------------------------- #
# Explicit failure: well-formed-but-unsupported and malformed input both raise.
# No silent pass-through, no coercion.
# --------------------------------------------------------------------------- #

# Well-formed indicators of types ARGUS does not classify yet. Each is a valid
# domain / URL / SHA-256, so this guards against a future type silently slipping
# through dispatch before its parser exists.
UNSUPPORTED: list[str] = [
    "example.com",  # domain
    "https://example.com/path",  # URL
    "hxxp://evil[.]com",  # defanged URL
    "a" * 64,  # 64 hex-ish chars resembling a SHA-256
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # SHA-256
    "::1",  # IPv6
]


@pytest.mark.parametrize("value", UNSUPPORTED)
def test_unsupported_but_wellformed_is_rejected(value: str) -> None:
    with pytest.raises(IocValidationError):
        parse_ioc(value)


# Malformed input dispatch surfaces as an IOC-layer failure, not an IPv4 one.
MALFORMED: list[str] = [
    "",  # empty
    "   ",  # whitespace only
    "999.999.999.999",  # IPv4 near-miss, octets out of range
    "010.0.0.1",  # leading-zero / octal-ambiguous (SSRF bypass candidate)
    "not-an-ioc",
]


@pytest.mark.parametrize("value", MALFORMED)
def test_malformed_input_is_rejected(value: str) -> None:
    with pytest.raises(IocValidationError):
        parse_ioc(value)


def test_validation_error_is_a_valueerror() -> None:
    with pytest.raises(ValueError, match="not a supported IOC"):
        parse_ioc("not-an-ioc")


# --------------------------------------------------------------------------- #
# Determinism + idempotency of the dispatch boundary itself.
# --------------------------------------------------------------------------- #


def test_dispatch_is_deterministic() -> None:
    assert parse_ioc("1.1.1.1") == parse_ioc("1.1.1.1")


def test_dispatch_round_trips_normalized_value() -> None:
    once = parse_ioc("8.8.8.8")
    twice = parse_ioc(once.normalized)
    assert twice.ioc_type == once.ioc_type
    assert twice == once
