"""Tests for the deterministic IPv4 IOC core (``argus.domain.ipv4``).

These parametrized tables double as the M1 deterministic-IOC eval fixtures
(``docs/EVALUATION.md`` §4, §19): positive, negative, boundary, special-use and
adversarial/near-miss cases, plus determinism/idempotency and provenance
invariants (cyber-domain-review). No dataset loader exists yet, so the fixtures
live here rather than in a separate file (that abstraction is deferred until a
second IOC type needs it).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from argus.domain.ipv4 import (
    Ipv4Ioc,
    Ipv4Scope,
    Ipv4ValidationError,
    parse_ipv4,
)

# --------------------------------------------------------------------------- #
# Scope classification — one deterministic category per address.
# Covers public, private, loopback, link-local, multicast, unspecified,
# broadcast, CGNAT (shared), documentation and reserved/special-use ranges.
# --------------------------------------------------------------------------- #

SCOPE_CASES: list[tuple[str, Ipv4Scope]] = [
    # Public / globally-routable unicast.
    ("8.8.8.8", Ipv4Scope.PUBLIC),
    ("1.1.1.1", Ipv4Scope.PUBLIC),
    ("203.0.114.1", Ipv4Scope.PUBLIC),  # just outside the 203.0.113/24 TEST-NET
    # RFC 1918 private.
    ("10.0.0.1", Ipv4Scope.PRIVATE),
    ("172.16.0.1", Ipv4Scope.PRIVATE),
    ("172.31.255.255", Ipv4Scope.PRIVATE),  # last address of 172.16/12
    ("192.168.1.1", Ipv4Scope.PRIVATE),
    # Loopback.
    ("127.0.0.1", Ipv4Scope.LOOPBACK),
    ("127.255.255.255", Ipv4Scope.LOOPBACK),  # last of 127/8
    # Link-local — including the cloud-metadata SSRF target.
    ("169.254.0.1", Ipv4Scope.LINK_LOCAL),
    ("169.254.169.254", Ipv4Scope.LINK_LOCAL),
    # Multicast.
    ("224.0.0.1", Ipv4Scope.MULTICAST),
    ("239.255.255.255", Ipv4Scope.MULTICAST),  # last of 224/4
    # Unspecified / broadcast singletons.
    ("0.0.0.0", Ipv4Scope.UNSPECIFIED),  # noqa: S104 — fixture string, not a bind addr
    ("255.255.255.255", Ipv4Scope.BROADCAST),
    # Shared / CGNAT (RFC 6598).
    ("100.64.0.1", Ipv4Scope.SHARED),
    ("100.127.255.255", Ipv4Scope.SHARED),  # last of 100.64/10
    # Documentation (RFC 5737 TEST-NET-1/2/3).
    ("192.0.2.1", Ipv4Scope.DOCUMENTATION),
    ("198.51.100.1", Ipv4Scope.DOCUMENTATION),
    ("203.0.113.1", Ipv4Scope.DOCUMENTATION),
    # Reserved / future-use / benchmarking — valid, not globally routable.
    ("240.0.0.1", Ipv4Scope.RESERVED),
    ("255.255.255.254", Ipv4Scope.RESERVED),  # 240/4, just below broadcast
    ("198.18.0.1", Ipv4Scope.RESERVED),  # RFC 2544 benchmarking
]


@pytest.mark.parametrize(("value", "expected"), SCOPE_CASES)
def test_scope_classification(value: str, expected: Ipv4Scope) -> None:
    assert parse_ipv4(value).scope is expected


# Boundary addresses: one step outside a special range must fall back to PUBLIC.
BOUNDARY_PUBLIC: list[str] = [
    "9.255.255.255",  # just below 10/8
    "11.0.0.0",  # just above 10/8
    "172.15.255.255",  # just below 172.16/12
    "172.32.0.0",  # just above 172.16/12
    "192.167.255.255",  # just below 192.168/16
    "192.169.0.0",  # just above 192.168/16
    "126.255.255.255",  # just below 127/8 loopback
    "128.0.0.0",  # just above 127/8 loopback
    "169.253.255.255",  # just below link-local
    "169.255.0.0",  # just above link-local
    "223.255.255.255",  # just below multicast 224/4
    "100.63.255.255",  # just below CGNAT 100.64/10
    "100.128.0.0",  # just above CGNAT 100.64/10
]


@pytest.mark.parametrize("value", BOUNDARY_PUBLIC)
def test_boundary_addresses_are_public(value: str) -> None:
    assert parse_ipv4(value).scope is Ipv4Scope.PUBLIC


# --------------------------------------------------------------------------- #
# External actionability — only PUBLIC is actionable; valid != actionable.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("value", "scope"), SCOPE_CASES)
def test_only_public_is_externally_actionable(value: str, scope: Ipv4Scope) -> None:
    ioc = parse_ipv4(value)
    assert ioc.externally_actionable is (scope is Ipv4Scope.PUBLIC)


def test_private_ip_is_not_externally_actionable() -> None:
    # A syntactically valid address is not automatically actionable (SSRF guard).
    assert parse_ipv4("10.0.0.5").externally_actionable is False


# --------------------------------------------------------------------------- #
# Negative / adversarial near-miss inputs — must fail explicitly.
# --------------------------------------------------------------------------- #

INVALID: list[str] = [
    "",  # empty
    "010.0.0.1",  # leading-zero / octal ambiguity (FP candidate: looks like an IP)
    "0x7f.0.0.1",  # hex octet
    "0xdeadbeef",  # hex integer
    "3232235521",  # bare decimal-integer form
    "192.168.0.1 ",  # trailing whitespace
    " 192.168.0.1",  # leading whitespace
    "192.168.0.1\n",  # embedded newline
    "192.168.1",  # too few octets
    "1.2.3.4.5",  # too many octets
    "256.1.1.1",  # octet out of range
    "999.999.999.999",  # all octets out of range
    "192.168.0.-1",  # negative octet
    "192.168.o.1",  # letter 'o' not digit
    "192.168.0.1/24",  # CIDR suffix
    "::1",  # IPv6, not IPv4
    "::ffff:192.168.0.1",  # IPv4-mapped IPv6
    "１９２.168.0.1",  # full-width unicode digits
    "1.1.1",  # three octets
]


@pytest.mark.parametrize("value", INVALID)
def test_invalid_inputs_are_rejected(value: str) -> None:
    with pytest.raises(Ipv4ValidationError):
        parse_ipv4(value)


def test_validation_error_is_a_valueerror() -> None:
    # Callers may catch the stdlib base; the message names the offending value.
    with pytest.raises(ValueError, match="not a valid IPv4 address"):
        parse_ipv4("not-an-ip")


# --------------------------------------------------------------------------- #
# Normalization: deterministic, idempotent, canonical.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("value", "_scope"), SCOPE_CASES)
def test_deterministic(value: str, _scope: Ipv4Scope) -> None:
    assert parse_ipv4(value) == parse_ipv4(value)


@pytest.mark.parametrize(("value", "_scope"), SCOPE_CASES)
def test_normalization_is_idempotent(value: str, _scope: Ipv4Scope) -> None:
    once = parse_ipv4(value)
    twice = parse_ipv4(once.normalized)
    assert twice.normalized == once.normalized
    assert twice.scope is once.scope


@pytest.mark.parametrize(("value", "_scope"), SCOPE_CASES)
def test_strict_input_normalizes_to_itself(value: str, _scope: Ipv4Scope) -> None:
    # Strict parsing admits exactly one textual form, so canonical == raw here.
    assert parse_ipv4(value).normalized == value


# --------------------------------------------------------------------------- #
# Provenance + value semantics.
# --------------------------------------------------------------------------- #


def test_raw_and_normalized_are_both_present() -> None:
    ioc = parse_ipv4("8.8.8.8")
    assert ioc.raw == "8.8.8.8"
    assert ioc.normalized == "8.8.8.8"
    assert isinstance(ioc, Ipv4Ioc)


def test_result_is_frozen() -> None:
    ioc = parse_ipv4("8.8.8.8")
    with pytest.raises(ValidationError):
        ioc.normalized = "1.1.1.1"
