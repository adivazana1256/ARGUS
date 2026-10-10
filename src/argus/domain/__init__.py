"""Domain layer: pure business types and rules.

Imports only stdlib + pydantic. No framework/SDK imports, no outer layers
(M0 spec §1.1).
"""

from argus.domain.domain import (
    DomainIoc,
    DomainScope,
    DomainValidationError,
    parse_domain,
)
from argus.domain.evidence import (
    CollectionStatus,
    EvidenceKind,
    EvidenceRecord,
    Provenance,
    observation_from_ioc,
)
from argus.domain.ioc import (
    Ioc,
    IocType,
    IocValidationError,
    parse_ioc,
)
from argus.domain.ipv4 import (
    Ipv4Ioc,
    Ipv4Scope,
    Ipv4ValidationError,
    parse_ipv4,
)

__all__ = [
    "CollectionStatus",
    "DomainIoc",
    "DomainScope",
    "DomainValidationError",
    "EvidenceKind",
    "EvidenceRecord",
    "Ioc",
    "IocType",
    "IocValidationError",
    "Ipv4Ioc",
    "Ipv4Scope",
    "Ipv4ValidationError",
    "Provenance",
    "observation_from_ioc",
    "parse_domain",
    "parse_ioc",
    "parse_ipv4",
]
