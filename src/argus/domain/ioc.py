"""Typed IOC entity layer + dispatch boundary (M1 Slice 2).

The application layer should hand a single raw observable string to one place and
get back a typed, classified IOC entity — or an explicit failure. That place is
:func:`parse_ioc`. Per-type validation/normalization lives in the type modules
(``argus.domain.ipv4``); this module only *dispatches* to them and names the set
of supported types. Stdlib + pydantic only (AGENTS.md; ``docs/ARCHITECTURE.md``
§1.1, §3).

Dependency direction is one-way: ``ioc`` imports the type modules, never the
reverse, so each type module stays an importable leaf. The ``Literal`` tag on
each entity (e.g. ``Ipv4Ioc.ioc_type``) mirrors an :class:`IocType` value and is
the discriminator a pydantic discriminated union will key on once a second type
exists.
"""

from __future__ import annotations

from enum import StrEnum

from argus.domain.domain import DomainIoc, DomainValidationError, parse_domain
from argus.domain.ipv4 import Ipv4Ioc, Ipv4ValidationError, parse_ipv4


class IocValidationError(ValueError):
    """Raised when a value matches no supported IOC type.

    A :class:`ValueError`, consistent with :class:`Ipv4ValidationError`, so
    callers may catch the stdlib base.
    """


class IocType(StrEnum):
    """Supported IOC types. One real member per type ARGUS can classify today."""

    IPV4 = "ipv4"
    DOMAIN = "domain"


# The IOC entity union. Plain union alias: it is a return annotation, not a
# validated field, so no pydantic discriminated union is needed yet — introduce
# that (keyed on ``ioc_type``) only once something validates an ``Ioc`` field.
type Ioc = Ipv4Ioc | DomainIoc


def parse_ioc(value: str) -> Ioc:
    """Detect the IOC type of a raw observable and return the typed entity.

    Tries each supported type in order; the first that accepts ``value`` wins.
    Raises :class:`IocValidationError` if no supported type matches — explicitly,
    never by silent coercion or pass-through.
    """
    # Ordered try-chain. IPv4 first (canonical numeric-dotted, narrowest), then
    # domain. `8.8.8.8` is valid as both, so order decides it stays an IPv4.
    # Replace with an ordered parser table once supported types exceed ~3.
    try:
        return parse_ipv4(value)
    except Ipv4ValidationError:
        pass
    try:
        return parse_domain(value)
    except DomainValidationError:
        raise IocValidationError(f"not a supported IOC: {value!r}") from None
