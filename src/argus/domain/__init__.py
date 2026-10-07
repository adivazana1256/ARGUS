"""Domain layer: pure business types and rules.

Imports only stdlib + pydantic. No framework/SDK imports, no outer layers
(M0 spec §1.1).
"""

from argus.domain.ipv4 import (
    Ipv4Ioc,
    Ipv4Scope,
    Ipv4ValidationError,
    parse_ipv4,
)

__all__ = [
    "Ipv4Ioc",
    "Ipv4Scope",
    "Ipv4ValidationError",
    "parse_ipv4",
]
