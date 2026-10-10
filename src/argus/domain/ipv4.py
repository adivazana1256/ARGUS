"""Deterministic IPv4 IOC core (M1 Slice 1).

Pure domain logic for a single IPv4 indicator of compromise: strict validation,
canonical normalization and scope/category classification. Stdlib
``ipaddress`` + pydantic only — no network, no wall-clock, no randomness
(AGENTS.md standing rules; ``docs/ARCHITECTURE.md`` §1.1, §3).

Design decisions worth knowing before changing this:

* **Strict parsing, ambiguous forms rejected.** We accept only what stdlib
  ``ipaddress.IPv4Address(str)`` accepts: canonical dotted-decimal. Leading-zero
  / octal / hex / bare-integer / CIDR / whitespace / unicode-digit forms are
  rejected, never coerced. The "leading zero means octal" interpretation is a
  classic SSRF filter-bypass, so an ambiguous IOC is a *rejected* IOC
  (cyber-domain-review; ``docs/SECURITY.md`` §8). A consequence: for every
  accepted input ``normalized == raw`` — there is only one textual form stdlib
  admits — but ``raw`` is kept distinct for the provenance model (§7) and for
  later IOC types (defanged/IPv6) where they will diverge.

* **Classification is explicit and ordered**, because stdlib categories overlap:
  ``0.0.0.0`` is both unspecified and "private"; ``169.254.169.254`` (the cloud
  metadata address) is link-local; ``255.255.255.255`` is reserved. The first
  rule in ``_classify`` that matches wins, so the scope is deterministic. Stdlib
  ``is_private`` is deliberately *not* used as the PRIVATE test — in 3.12 it also
  covers documentation and benchmarking ranges — so PRIVATE/SHARED/DOCUMENTATION
  use explicit RFC networks.

* **A syntactically valid IPv4 is not automatically externally actionable.**
  Only globally-routable unicast (scope PUBLIC) is actionable; private,
  loopback, link-local, multicast, reserved, broadcast, CGNAT, documentation and
  unspecified addresses are not.
"""

from __future__ import annotations

import ipaddress
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Ipv4ValidationError(ValueError):
    """Raised when a value is not a strictly-valid canonical IPv4 address."""


class Ipv4Scope(StrEnum):
    """IPv4 address category. One deterministic scope per address."""

    PUBLIC = "public"  # globally-routable unicast
    PRIVATE = "private"  # RFC 1918
    LOOPBACK = "loopback"  # 127.0.0.0/8
    LINK_LOCAL = "link_local"  # 169.254.0.0/16 (incl. cloud metadata)
    MULTICAST = "multicast"  # 224.0.0.0/4
    UNSPECIFIED = "unspecified"  # 0.0.0.0
    BROADCAST = "broadcast"  # 255.255.255.255
    SHARED = "shared"  # RFC 6598 CGNAT 100.64.0.0/10
    DOCUMENTATION = "documentation"  # RFC 5737 TEST-NET
    RESERVED = "reserved"  # not globally routable and none of the above


_BROADCAST = ipaddress.IPv4Address("255.255.255.255")
_SHARED = ipaddress.IPv4Network("100.64.0.0/10")
_DOCUMENTATION = (
    ipaddress.IPv4Network("192.0.2.0/24"),
    ipaddress.IPv4Network("198.51.100.0/24"),
    ipaddress.IPv4Network("203.0.113.0/24"),
)
_PRIVATE = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)


def _classify(addr: ipaddress.IPv4Address) -> Ipv4Scope:
    """Map an address to its scope. Order is significant (first match wins)."""
    if addr.is_unspecified:
        return Ipv4Scope.UNSPECIFIED
    if addr == _BROADCAST:
        return Ipv4Scope.BROADCAST
    if addr.is_loopback:
        return Ipv4Scope.LOOPBACK
    if addr.is_link_local:
        return Ipv4Scope.LINK_LOCAL
    if addr.is_multicast:
        return Ipv4Scope.MULTICAST
    if any(addr in net for net in _DOCUMENTATION):
        return Ipv4Scope.DOCUMENTATION
    if addr in _SHARED:
        return Ipv4Scope.SHARED
    if any(addr in net for net in _PRIVATE):
        return Ipv4Scope.PRIVATE
    if addr.is_global:
        return Ipv4Scope.PUBLIC
    return Ipv4Scope.RESERVED


class Ipv4Ioc(BaseModel):
    """Structured result of classifying one IPv4 indicator.

    ``raw`` (provenance: the value as observed) stays distinct from
    ``normalized`` (canonical dotted-decimal) so this can slot into the ARGUS
    Evidence model later (``docs/ARCHITECTURE.md`` §7) without losing the
    original string. Frozen: a classified IOC is an immutable value.
    """

    model_config = ConfigDict(frozen=True)

    # Discriminator tag for the IOC entity layer (``argus.domain.ioc``). Kept as a
    # Literal, not ``IocType``, so this module stays a leaf (stdlib + pydantic
    # only): importing the enum would create an ``ioc`` <-> ``ipv4`` cycle. The
    # string mirrors ``IocType.IPV4`` — the one deliberate duplication.
    ioc_type: Literal["ipv4"] = "ipv4"
    raw: str
    normalized: str
    scope: Ipv4Scope
    externally_actionable: bool


def parse_ipv4(value: str) -> Ipv4Ioc:
    """Validate, normalize and classify a single IPv4 string.

    Returns an :class:`Ipv4Ioc`. Raises :class:`Ipv4ValidationError` on any input
    that is not a strictly-valid canonical IPv4 address — explicitly, never by
    silent coercion.
    """
    try:
        addr = ipaddress.IPv4Address(value)
    except ValueError as exc:  # AddressValueError subclasses ValueError
        raise Ipv4ValidationError(f"not a valid IPv4 address: {value!r}") from exc
    scope = _classify(addr)
    return Ipv4Ioc(
        raw=value,
        normalized=str(addr),
        scope=scope,
        externally_actionable=scope is Ipv4Scope.PUBLIC,
    )
