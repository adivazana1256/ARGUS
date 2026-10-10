"""Threat-intelligence collection orchestration (M1 Slice 4).

The first working collection pipeline: a validated typed :class:`Ioc` is handed
to one or more :class:`ThreatIntelProvider` adapters, their untrusted responses
are mapped into the existing immutable :class:`EvidenceRecord` sink, and the
whole attempt is summarized as a :class:`CollectionResult` whose
:class:`CollectionOutcome` distinguishes success, no-findings, partial and total
failure. Application layer: imports ``domain`` only, never ``infrastructure`` or
``api`` (``docs/ARCHITECTURE.md`` §1.1, §4; enforced by ``tests/architecture/``).

Design decisions worth knowing before changing this (approved architecture gate):

* **External source ⇒ CLAIM, always.** Every provider-sourced record is minted
  with :attr:`EvidenceKind.CLAIM` — including empty and failed collections. A
  provider is an untrusted external source; nothing it returns is an ARGUS-derived
  fact. ARGUS-derived facts come only from ``observation_from_ioc``. Because
  ``kind`` is frozen and part of ``evidence_id``, a provider that tries to spoof
  ``source="argus.domain.ioc"`` still yields a distinct CLAIM id — source-spoofing
  (``T-AI-004``) is structurally defeated, not merely checked. This preserves the
  observation/verdict split: a provider's "malicious" is a *claim*, never a
  verdict (``docs/SECURITY.md`` §6; ``docs/ARCHITECTURE.md`` §7).

* **The orchestrator owns provenance, not the response body.** ``provenance.source``
  is taken from the trusted, registered ``provider.name`` — never from any field
  inside the untrusted :class:`ProviderResponse`. A response cannot name its own
  source (``T-TOOL-003`` tool-output injection).

* **Provider data is untrusted input at the boundary.** Responses are validated
  and bounded by pydantic; mapping into :class:`EvidenceRecord` re-validates and
  re-bounds. A malformed/oversized response is caught and becomes a FAILURE
  record — never a crash, never a partial write, never fabricated evidence
  (``T-TOOL-002``). Payload strings are inert ``dict[str, str]`` data; they are
  stored, never interpreted or executed (``T-TOOL-003``).

* **Absence is never silently benign.** ``NOT_FOUND`` maps to a CLAIM/EMPTY record
  with no payload and a :attr:`CollectionOutcome.NO_FINDINGS` outcome — distinct
  from a claimed-benign finding. And when *no* provider can even look at the IOC,
  the outcome is :attr:`CollectionOutcome.FAILURE`, not NO_FINDINGS: "nobody could
  look" is not "nobody found anything".

* **No network, no clock, no retries.** The clock is injected (``collected_at``);
  the loop is sequential and deterministic. Timeout/retry/rate-limit abstractions
  are deliberately deferred — there is nothing offline to time out (ponytail: add
  when a real network adapter justifies it).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, field_validator

from argus.domain.evidence import (
    CollectionStatus,
    EvidenceKind,
    EvidenceRecord,
    Provenance,
)
from argus.domain.ioc import Ioc, IocType
from argus.domain.ipv4 import Ipv4Ioc

# Bounds for an untrusted provider response. A provider may enrich one IOC with a
# handful of records (e.g. multiple detections); an unbounded list is a DoS vector.
# Per-record field bounds are enforced downstream by EvidenceRecord's map bounds.
_MAX_RECORDS = 16
_MAX_REFERENCE = 512
# Payload key under which a provider's claimed classification is stored. Named to
# make the fact/claim boundary legible in the stored evidence: this is what the
# source *claims*, not a verdict ARGUS reached.
CLAIMED_VERDICT_KEY = "claimed_verdict"


class ProviderResponseStatus(StrEnum):
    """Outcome a provider reports for a single IOC lookup (untrusted)."""

    FOUND = "found"  # provider has data; ``records`` carries the claim(s)
    NOT_FOUND = "not_found"  # provider ran, has no data on this IOC
    UNAVAILABLE = "unavailable"  # provider could not answer (simulated outage)


class ProviderError(Exception):
    """A provider failed to produce a usable response.

    Raised by a provider for an outage, a transport failure, or an unsupported
    IOC type. The orchestrator converts it into a FAILURE evidence record — it
    never propagates as an unhandled crash and never yields fabricated data.
    """


@runtime_checkable
class ThreatIntelProvider(Protocol):
    """Minimal typed contract every threat-intel adapter satisfies.

    Deliberately tiny: a name (used as the trusted evidence ``source``), the set
    of IOC types it can answer, and a single ``query``. No registry, no discovery,
    no lifecycle — adapters are passed to :func:`collect` as an explicit list.
    """

    name: str
    supported_types: frozenset[IocType]

    def query(self, ioc: Ioc) -> ProviderResponse:
        """Look up one IOC. Raise :class:`ProviderError` on failure/unsupported."""
        ...


class ProviderResponse(BaseModel):
    """One provider's untrusted answer about a single IOC.

    Frozen and bounded: this is an external trust boundary. ``records`` is present
    only for :attr:`ProviderResponseStatus.FOUND`; each record is a bounded string
    map re-validated when mapped into an :class:`EvidenceRecord`.
    """

    model_config = ConfigDict(frozen=True)

    status: ProviderResponseStatus
    records: tuple[dict[str, str], ...] = ()
    reference: str | None = None  # provider's opaque record locator, bounded

    @field_validator("records")
    @classmethod
    def _bound_records(
        cls, value: tuple[dict[str, str], ...]
    ) -> tuple[dict[str, str], ...]:
        if len(value) > _MAX_RECORDS:
            raise ValueError(f"at most {_MAX_RECORDS} records allowed")
        return value

    @field_validator("reference")
    @classmethod
    def _bound_reference(cls, value: str | None) -> str | None:
        if value is not None and len(value) > _MAX_REFERENCE:
            raise ValueError(f"reference must be at most {_MAX_REFERENCE} chars")
        return value


class CollectionOutcome(StrEnum):
    """Aggregate result of collecting from every capable provider for one IOC."""

    SUCCESS = "success"  # at least one finding, no provider failed
    NO_FINDINGS = "no_findings"  # providers ran, none had data (never "benign")
    PARTIAL = "partial"  # some findings/empty, but at least one provider failed
    FAILURE = "failure"  # every attempt failed, or no provider could look


class CollectionResult(BaseModel):
    """Structured, inspectable result of one collection run over one IOC.

    Frozen aggregate over the immutable evidence the run produced. It does not
    duplicate evidence identity/serialization/provenance — those live on each
    embedded :class:`EvidenceRecord`.
    """

    model_config = ConfigDict(frozen=True)

    subject: Ioc
    outcome: CollectionOutcome
    evidence: tuple[EvidenceRecord, ...] = ()
    providers_queried: tuple[str, ...] = ()


def _claim(
    *,
    ioc: Ioc,
    source: str,
    status: CollectionStatus,
    collected_at: datetime,
    payload: dict[str, str] | None = None,
    error: str | None = None,
    reference: str | None = None,
    investigation_id: str | None = None,
) -> EvidenceRecord:
    """Mint one provider-sourced CLAIM record.

    ``kind`` is pinned to CLAIM and ``source`` is the trusted provider name — a
    provider can set neither. Re-validates/re-bounds through ``EvidenceRecord``.
    """
    return EvidenceRecord(
        kind=EvidenceKind.CLAIM,
        status=status,
        subject=ioc,
        provenance=Provenance(
            source=source,
            collected_at=collected_at,
            source_reference=reference,
        ),
        payload=payload,
        error=error,
        investigation_id=investigation_id,
        metadata={},
    )


def _map_response(
    *,
    ioc: Ioc,
    source: str,
    response: ProviderResponse,
    collected_at: datetime,
    investigation_id: str | None,
) -> list[EvidenceRecord]:
    """Convert one validated provider response into evidence record(s)."""
    if response.status is ProviderResponseStatus.UNAVAILABLE:
        return [
            _claim(
                ioc=ioc,
                source=source,
                status=CollectionStatus.FAILURE,
                collected_at=collected_at,
                error="provider unavailable",
                investigation_id=investigation_id,
            )
        ]
    if response.status is ProviderResponseStatus.NOT_FOUND:
        return [
            _claim(
                ioc=ioc,
                source=source,
                status=CollectionStatus.EMPTY,
                collected_at=collected_at,
                reference=response.reference,
                investigation_id=investigation_id,
            )
        ]
    # FOUND: one CLAIM/SUCCESS record per claimed observation. A FOUND response
    # with no records still asserts a finding exists but carries nothing usable —
    # treat it as EMPTY rather than inventing a payload.
    if not response.records:
        return [
            _claim(
                ioc=ioc,
                source=source,
                status=CollectionStatus.EMPTY,
                collected_at=collected_at,
                reference=response.reference,
                investigation_id=investigation_id,
            )
        ]
    return [
        _claim(
            ioc=ioc,
            source=source,
            status=CollectionStatus.SUCCESS,
            collected_at=collected_at,
            payload=record,
            reference=response.reference,
            investigation_id=investigation_id,
        )
        for record in response.records
    ]


def _outcome(
    evidence: Sequence[EvidenceRecord], *, had_capable: bool
) -> CollectionOutcome:
    """Derive the aggregate outcome from the produced evidence."""
    if not had_capable:
        # Nobody could even look — distinct from "nobody found anything".
        return CollectionOutcome.FAILURE
    statuses = {ev.status for ev in evidence}
    if statuses == {CollectionStatus.FAILURE}:
        return CollectionOutcome.FAILURE
    if CollectionStatus.FAILURE in statuses:
        return CollectionOutcome.PARTIAL
    if CollectionStatus.SUCCESS in statuses:
        return CollectionOutcome.SUCCESS
    return CollectionOutcome.NO_FINDINGS


def collect(
    ioc: Ioc,
    providers: Sequence[ThreatIntelProvider],
    *,
    collected_at: datetime,
    investigation_id: str | None = None,
) -> CollectionResult:
    """Collect threat intel for one validated IOC from every capable provider.

    Only providers that declare support for ``ioc.ioc_type`` are queried. Each
    provider failure (``ProviderError`` or a malformed response that fails
    validation) becomes a FAILURE evidence record — never a crash, never
    fabricated data. The clock is injected; the run is deterministic.
    """
    ioc_type = _ioc_type(ioc)
    capable = [p for p in providers if ioc_type in p.supported_types]

    evidence: list[EvidenceRecord] = []
    for provider in capable:
        try:
            response = provider.query(ioc)
            evidence.extend(
                _map_response(
                    ioc=ioc,
                    source=provider.name,
                    response=response,
                    collected_at=collected_at,
                    investigation_id=investigation_id,
                )
            )
        except (ProviderError, ValueError) as exc:
            # ProviderError = declared failure; ValueError = a response that broke
            # schema/bounds validation. Both fail safe to a bounded FAILURE record.
            evidence.append(
                _claim(
                    ioc=ioc,
                    source=provider.name,
                    status=CollectionStatus.FAILURE,
                    collected_at=collected_at,
                    error=_safe_error(exc),
                    investigation_id=investigation_id,
                )
            )

    return CollectionResult(
        subject=ioc,
        outcome=_outcome(evidence, had_capable=bool(capable)),
        evidence=tuple(evidence),
        providers_queried=tuple(p.name for p in capable),
    )


def _ioc_type(ioc: Ioc) -> IocType:
    """Map a typed IOC entity to its :class:`IocType` via its discriminator tag."""
    return IocType.IPV4 if isinstance(ioc, Ipv4Ioc) else IocType.DOMAIN


def _safe_error(exc: Exception) -> str:
    """A bounded, non-leaky error string for a FAILURE record.

    We keep a short reason but never the full exception context; the evidence
    model also bounds this field. For a validation failure we record a generic
    reason rather than echoing untrusted input back into stored evidence.
    """
    if isinstance(exc, ProviderError):
        return str(exc)[:256] or "provider error"
    return "invalid provider response"
