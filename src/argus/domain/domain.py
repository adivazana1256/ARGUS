"""Deterministic domain-name IOC core (M1 Slice 3).

Pure domain logic for a single domain-name indicator of compromise: strict
syntactic validation, canonical normalization and special-use/actionability
classification. Stdlib ``re`` + pydantic only — no network, no DNS lookup, no
wall-clock, no randomness (AGENTS.md standing rules; ``docs/ARCHITECTURE.md``
§1.1, §3).

Design decisions worth knowing before changing this:

* **Strict LDH, ambiguous forms rejected.** We accept only the preferred-name
  syntax (RFC 952 / 1123): ASCII letter-digit-hyphen labels, 1–63 chars each,
  no leading/trailing hyphen, total ≤253. Whitespace, empty labels (``a..b``),
  underscores, and any non-ASCII input are rejected, never coerced — an
  ambiguous IOC is a *rejected* IOC (cyber-domain-review; the IPv4 core takes
  the same stance).

* **Unicode/IDN is rejected; punycode A-labels are accepted.** ``xn--`` labels
  are ordinary ASCII LDH and pass. Raw Unicode (U-label) input is rejected
  outright: the stdlib only ships flaky IDNA-2003, encoding Unicode ourselves
  would invite homograph/normalization nondeterminism, and we never decode
  punycode back to Unicode. Consequence: a malicious Unicode IDN submitted as
  U-labels is rejected rather than classified (``raw`` is preserved). Lifting
  this to IDNA-2008 is a later slice — do not add it here without a decision.

* **Rightmost label must not be all-numeric.** Real DNS rule (TLDs are never
  all-numeric) and the clean disambiguator from IPv4: it keeps ``999.999.999.999``
  and ``010.0.0.1`` — which fail IPv4 parsing — from leaking through as
  "domains".

* **Canonical form = ASCII-lowercase, trailing dot stripped.** One optional
  trailing dot (the DNS root / FQDN marker) is accepted and removed. Unlike the
  IPv4 core, ``raw`` and ``normalized`` genuinely diverge here (case, trailing
  dot), which is exactly the provenance split the Evidence model anticipates
  (``docs/ARCHITECTURE.md`` §7).

* **A syntactically valid domain is not automatically externally actionable.**
  Only ordinary (PUBLIC) domains are actionable; special-use (localhost, mDNS
  ``.local``, Tor ``.onion``, RFC 2606/6761 ``.invalid``/``.test``, reverse-DNS
  ``.arpa``, ICANN private-use ``.internal``) and documentation (``.example``,
  ``example.com/.net/.org``) names are not — they are non-resolvable, reserved,
  or resolve to internal hosts, and treating any of them as actionable is an
  SSRF foot-gun (``docs/SECURITY.md`` §8).

  The special-use set is a denylist of names that may resolve internally;
  anything unmatched defaults to PUBLIC/actionable. That default is deliberate:
  inverting to an allowlist needs a public-suffix list (data + dependency,
  deferred past M1), and this flag is a classification signal — the actual SSRF
  *enforcement* is owned at the outbound-fetch boundary, not here. No PSL is
  used, so registrable-domain-vs-subdomain is not distinguished.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

# RFC 952 / 1123 preferred-name label: ASCII LDH, no leading/trailing hyphen.
# Applied to an already-lowercased label, so the class is lowercase only.
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?")
_MAX_TOTAL = 253  # octets, excluding the root/trailing dot
_MAX_LABEL = 63


class DomainValidationError(ValueError):
    """Raised when a value is not a strictly-valid canonical domain name."""


class DomainScope(StrEnum):
    """Domain-name category. One deterministic scope per name."""

    PUBLIC = "public"  # ordinary resolvable-looking domain
    SPECIAL_USE = "special_use"  # localhost / .local / .onion / .invalid / .test
    DOCUMENTATION = "documentation"  # .example and example.com/.net/.org (RFC 2606)


# IANA Special-Use Domain Names (RFC 6761/6762/7686/8375) + the ICANN-reserved
# private-use `.internal` (2024): TLDs that are never ordinary public domains and
# may resolve to internal hosts, so they must not be externally actionable (SSRF,
# docs/SECURITY.md §8). `arpa` covers in-addr.arpa / ip6.arpa / home.arpa via the
# rightmost-label match; `internal` covers `*.internal`.
_SPECIAL_TLDS = frozenset({"local", "onion", "invalid", "test", "arpa", "internal"})
# RFC 6761 documentation TLD.
_DOCUMENTATION_TLDS = frozenset({"example"})
# RFC 2606 reserved second-level documentation domains.
_DOCUMENTATION_DOMAINS = frozenset({"example.com", "example.net", "example.org"})


def _classify(normalized: str, labels: list[str]) -> DomainScope:
    """Map a normalized name to its scope. Order is significant (first match)."""
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return DomainScope.SPECIAL_USE
    tld = labels[-1]
    if tld in _SPECIAL_TLDS:
        return DomainScope.SPECIAL_USE
    if tld in _DOCUMENTATION_TLDS or normalized in _DOCUMENTATION_DOMAINS:
        return DomainScope.DOCUMENTATION
    return DomainScope.PUBLIC


class DomainIoc(BaseModel):
    """Structured result of classifying one domain-name indicator.

    ``raw`` (the value as observed) stays distinct from ``normalized`` (canonical
    ASCII-lowercase, trailing dot stripped) for the Evidence model
    (``docs/ARCHITECTURE.md`` §7). Frozen: a classified IOC is an immutable value.
    """

    model_config = ConfigDict(frozen=True)

    # Discriminator tag for the IOC entity layer (``argus.domain.ioc``). A
    # ``Literal`` rather than ``IocType`` so this module stays a leaf (stdlib +
    # pydantic only) and no ``ioc`` <-> ``domain`` import cycle forms. The string
    # mirrors ``IocType.DOMAIN`` — the one deliberate duplication.
    ioc_type: Literal["domain"] = "domain"
    raw: str
    normalized: str
    scope: DomainScope
    externally_actionable: bool


def parse_domain(value: str) -> DomainIoc:
    """Validate, normalize and classify a single domain-name string.

    Returns a :class:`DomainIoc`. Raises :class:`DomainValidationError` on any
    input that is not a strictly-valid canonical domain name — explicitly, never
    by silent coercion.
    """
    if not value or not value.isascii():
        raise DomainValidationError(f"not a valid domain: {value!r}")

    # One optional trailing dot (DNS root) is accepted; everything else is
    # validated as-is so embedded/leading whitespace and double dots fail below.
    candidate = value[:-1] if value.endswith(".") else value
    if not candidate or len(candidate) > _MAX_TOTAL:
        raise DomainValidationError(f"not a valid domain: {value!r}")

    labels = candidate.lower().split(".")
    # Single-label names are only valid for recognized specials (e.g. localhost).
    if len(labels) < 2 and labels != ["localhost"]:
        raise DomainValidationError(f"not a valid domain: {value!r}")
    for label in labels:
        if not 1 <= len(label) <= _MAX_LABEL or not _LABEL.fullmatch(label):
            raise DomainValidationError(f"not a valid domain: {value!r}")
    # TLDs are never all-numeric; this also rejects IPv4 near-misses (010.0.0.1).
    if labels[-1].isdigit():
        raise DomainValidationError(f"not a valid domain: {value!r}")

    normalized = ".".join(labels)
    scope = _classify(normalized, labels)
    return DomainIoc(
        raw=value,
        normalized=normalized,
        scope=scope,
        externally_actionable=scope is DomainScope.PUBLIC,
    )
