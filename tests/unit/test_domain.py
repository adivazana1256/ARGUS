"""Tests for the deterministic domain-name IOC core (``argus.domain.domain``).

These parametrized tables double as the M1 deterministic-IOC eval fixtures
(``docs/EVALUATION.md`` §4, §19): positive, negative, boundary, special-use and
adversarial/near-miss cases, plus determinism/idempotency and provenance
invariants (cyber-domain-review). They live here, alongside the type, until a
second IOC type needs a shared dataset loader (deferred, as with IPv4).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from argus.domain.domain import (
    DomainIoc,
    DomainScope,
    DomainValidationError,
    parse_domain,
)

# --------------------------------------------------------------------------- #
# Scope classification — one deterministic category per name.
# Covers public, special-use (localhost/.local/.onion/.invalid/.test) and
# documentation (.example, example.com/.net/.org).
# --------------------------------------------------------------------------- #

SCOPE_CASES: list[tuple[str, DomainScope]] = [
    # Ordinary / public.
    ("example.org.uk", DomainScope.PUBLIC),
    ("sub.deep.example.co", DomainScope.PUBLIC),
    ("xn--80ak6aa92e.com", DomainScope.PUBLIC),  # punycode A-label (IDN, pre-encoded)
    ("a.io", DomainScope.PUBLIC),  # minimal two-label
    ("host123.net", DomainScope.PUBLIC),  # digits in a label are fine
    ("1foo.com", DomainScope.PUBLIC),  # label may start with a digit (RFC 1123)
    # Special-use (RFC 6761/6762/7686/2606).
    ("localhost", DomainScope.SPECIAL_USE),
    ("api.localhost", DomainScope.SPECIAL_USE),
    ("printer.local", DomainScope.SPECIAL_USE),  # mDNS
    ("3g2upl4pq6kufc4m.onion", DomainScope.SPECIAL_USE),  # Tor
    ("nothing.invalid", DomainScope.SPECIAL_USE),
    ("unit.test", DomainScope.SPECIAL_USE),
    # Documentation (RFC 2606 / 6761).
    ("example.com", DomainScope.DOCUMENTATION),
    ("example.net", DomainScope.DOCUMENTATION),
    ("example.org", DomainScope.DOCUMENTATION),
    ("anything.example", DomainScope.DOCUMENTATION),
    ("www.example.com", DomainScope.PUBLIC),  # only the exact 2LDs are reserved
]


@pytest.mark.parametrize(("value", "expected"), SCOPE_CASES)
def test_scope_classification(value: str, expected: DomainScope) -> None:
    assert parse_domain(value).scope is expected


# --------------------------------------------------------------------------- #
# External actionability — only PUBLIC is actionable; valid != actionable.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("value", "scope"), SCOPE_CASES)
def test_only_public_is_externally_actionable(value: str, scope: DomainScope) -> None:
    ioc = parse_domain(value)
    assert ioc.externally_actionable is (scope is DomainScope.PUBLIC)


def test_localhost_is_not_externally_actionable() -> None:
    # A syntactically valid name is not automatically actionable (SSRF guard).
    assert parse_domain("localhost").externally_actionable is False


# --------------------------------------------------------------------------- #
# Negative / adversarial near-miss inputs — must fail explicitly.
# --------------------------------------------------------------------------- #

INVALID: list[str] = [
    "",  # empty
    "   ",  # whitespace only
    "example .com",  # embedded space
    " example.com",  # leading whitespace
    "example.com ",  # trailing whitespace
    "example.com\n",  # embedded newline
    "example..com",  # empty label
    ".example.com",  # leading dot / empty first label
    "example.com..",  # double trailing dot
    "com",  # bare single label (not a recognized special)
    "notadomain",  # single label, no dot
    "a" * 64 + ".com",  # label over 63 chars
    ("a." * 127) + "a",  # total length over 253 octets
    "exa_mple.com",  # underscore is not LDH
    "-example.com",  # leading hyphen in a label
    "example-.com",  # trailing hyphen in a label
    "example.com/path",  # slash / path
    "https://example.com",  # scheme
    "user@example.com",  # userinfo
    "evil[.]com",  # defanged
    "example(dot)com",  # defanged
    "xn--.com",  # empty punycode label body
    "café.com",  # raw Unicode U-label (IDN rejected for M1)
    "例え.テスト",  # raw Unicode
    "１２３.com",  # full-width unicode digits
    "999.999.999.999",  # all-numeric labels (IPv4 near-miss)
    "010.0.0.1",  # leading-zero / octal-ambiguous (also an IPv4 near-miss)
    "123.456",  # all-numeric rightmost label
]


@pytest.mark.parametrize("value", INVALID)
def test_invalid_inputs_are_rejected(value: str) -> None:
    with pytest.raises(DomainValidationError):
        parse_domain(value)


def test_validation_error_is_a_valueerror() -> None:
    # Callers may catch the stdlib base; the message names the offending value.
    with pytest.raises(ValueError, match="not a valid domain"):
        parse_domain("not a domain")


# --------------------------------------------------------------------------- #
# Boundary: labels/length right at the accepted limits must pass.
# --------------------------------------------------------------------------- #

BOUNDARY_VALID: list[str] = [
    ("a" * 63) + ".com",  # label exactly 63 chars
    ("a." * 125) + "co",  # total exactly 253 octets
    "x.yz",  # two one/two-char labels
]


@pytest.mark.parametrize("value", BOUNDARY_VALID)
def test_boundary_valid_inputs_accepted(value: str) -> None:
    assert parse_domain(value).scope is DomainScope.PUBLIC


# --------------------------------------------------------------------------- #
# Normalization: deterministic, idempotent, canonical (lowercase, no trailing dot).
# --------------------------------------------------------------------------- #

NORMALIZE_CASES: list[tuple[str, str]] = [
    ("Example.COM", "example.com"),  # case-fold
    ("example.com.", "example.com"),  # trailing dot (FQDN root) stripped
    ("WWW.Example.ORG.", "www.example.org"),  # both
    ("LOCALHOST", "localhost"),
]


@pytest.mark.parametrize(("value", "expected"), NORMALIZE_CASES)
def test_normalization_canonical_form(value: str, expected: str) -> None:
    assert parse_domain(value).normalized == expected


@pytest.mark.parametrize(("value", "_expected"), NORMALIZE_CASES)
def test_trailing_dot_and_case_do_not_change_scope(value: str, _expected: str) -> None:
    # example.com. and example.com classify identically.
    assert parse_domain(value).scope is parse_domain(_expected).scope


@pytest.mark.parametrize(("value", "_scope"), SCOPE_CASES)
def test_deterministic(value: str, _scope: DomainScope) -> None:
    assert parse_domain(value) == parse_domain(value)


@pytest.mark.parametrize(("value", "_scope"), SCOPE_CASES)
def test_normalization_is_idempotent(value: str, _scope: DomainScope) -> None:
    once = parse_domain(value)
    twice = parse_domain(once.normalized)
    assert twice.normalized == once.normalized
    assert twice.scope is once.scope


# --------------------------------------------------------------------------- #
# Provenance + value semantics.
# --------------------------------------------------------------------------- #


def test_raw_and_normalized_diverge_but_both_present() -> None:
    ioc = parse_domain("Example.COM.")
    assert ioc.raw == "Example.COM."  # provenance: exactly as observed
    assert ioc.normalized == "example.com"  # canonical
    assert isinstance(ioc, DomainIoc)


def test_result_is_frozen() -> None:
    ioc = parse_domain("example.org")
    with pytest.raises(ValidationError):
        ioc.normalized = "evil.com"
