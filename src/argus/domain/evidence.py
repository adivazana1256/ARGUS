"""Deterministic Evidence Core (M1).

Wraps a deterministic IOC investigation result as an immutable, provenance-bearing
evidence record. Stdlib + pydantic only — no network, no wall-clock, no randomness,
no external threat-intel (AGENTS.md standing rules; ``docs/ARCHITECTURE.md`` §1.1,
§7). This is the structured sink investigation results flow into; it is *not* the
threat-intel collection layer, and nothing here reaches outward.

Design decisions worth knowing before changing this (approved architecture gate):

* **Fact vs claim is structural and immutable.** :attr:`EvidenceKind.OBSERVATION`
  is a fact ARGUS derived deterministically (e.g. an IOC classification);
  :attr:`EvidenceKind.CLAIM` is an assertion an external source made — untrusted.
  ``kind`` is frozen *and* part of ``evidence_id``, so a claim can never be
  silently rewritten into an ARGUS fact: "promoting" one necessarily mints a new,
  distinct, separately-attributable record, and the original is never mutated.
  This is the core control behind ``T-AI-004`` hallucinated evidence
  (``docs/SECURITY.md`` §6) and the §7 raw/claim/finding separation.

* **Trust-grading and confidence scoring deliberately do NOT live here.** Evidence
  records *what was collected and from where*; deciding how much to believe it is a
  later verification/correlation policy. A numeric confidence at this layer would
  invite weighting a claim as a fact — exactly the boundary this slice protects.

* **Collection outcome is first-class.** A failed or empty collection is a
  provenance-bearing record (:class:`CollectionStatus`), never a dropped exception
  — absence of data is itself evidence and must not be silently filled in.

* **The wall-clock is injected.** ``collected_at`` is supplied by the caller and
  must be timezone-aware; it is normalized to UTC. The domain never reads the clock
  (determinism). It is collection metadata, not identity (below).

* **Identity is deterministic and content-addressed.** ``evidence_id`` is a sha256
  over the canonical identity tuple and EXCLUDES ``collected_at``,
  ``investigation_id`` and ``metadata`` — so the same claim from the same source
  about the same subject dedupes across time and across investigations. It is
  derived, never a caller input: it is recomputed on every load, so a persisted
  record cannot be tampered to carry a mismatched id.

* **All external/untrusted strings and maps are bounded at construction.** Oversized
  or malformed source metadata is rejected, not stored — every future external
  evidence payload is treated as untrusted input at this boundary.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from argus.domain.ioc import Ioc

# Bounds for untrusted source metadata. Deliberately conservative: source claims
# are untrusted input, and an unbounded map/string is an oversize/DoS vector.
_MAX_STR = 512  # source, source_reference, tool_run_id, error, investigation_id
_MAX_META_KEYS = 32
_MAX_KEY = 128
_MAX_VALUE = 1024


class EvidenceKind(StrEnum):
    """Origin of an evidence record. Immutable; part of ``evidence_id``."""

    OBSERVATION = "observation"  # a fact ARGUS derived deterministically
    CLAIM = "claim"  # an assertion an external source made (untrusted)


class CollectionStatus(StrEnum):
    """Outcome of the collection that produced this record."""

    SUCCESS = "success"  # data collected; payload may be present
    EMPTY = "empty"  # collection ran, found nothing (no payload) — absence is evidence
    FAILURE = "failure"  # collection failed; carries an error, no payload


class Provenance(BaseModel):
    """Where an evidence record came from and when it was collected.

    Provenance cannot be accidentally discarded: it is a required, frozen component
    of every :class:`EvidenceRecord`. It carries no trust grade — see the module
    docstring. Frozen: a recorded provenance is an immutable value.
    """

    model_config = ConfigDict(frozen=True)

    source: str  # who/what produced this (e.g. "argus.domain.ioc"); bounded
    collected_at: datetime  # tz-aware, normalized to UTC; injected, never read here
    source_reference: str | None = None  # opaque where-from (record id / locator)
    tool_run_id: str | None = None  # opaque collection-run id, if any

    @field_validator("source")
    @classmethod
    def _check_source(cls, value: str) -> str:
        if not value or len(value) > _MAX_STR:
            raise ValueError(f"source must be 1..{_MAX_STR} chars")
        return value

    @field_validator("source_reference", "tool_run_id")
    @classmethod
    def _check_optional_str(cls, value: str | None) -> str | None:
        if value is not None and len(value) > _MAX_STR:
            raise ValueError(f"value must be at most {_MAX_STR} chars")
        return value

    @field_validator("collected_at")
    @classmethod
    def _require_aware_utc(cls, value: datetime) -> datetime:
        # Naive datetimes are ambiguous and non-deterministic across hosts; reject
        # them, never assume a zone. Aware values are canonicalized to UTC.
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must be timezone-aware")
        return value.astimezone(UTC)


class EvidenceRecord(BaseModel):
    """One immutable, provenance-bearing unit of collected evidence.

    ``subject`` is the typed, already-validated indicator the evidence is *about*;
    ``payload`` is the data collected about it (``None`` for a pure classification
    observation, whose facts already live in ``subject``). Frozen: evidence is never
    mutated — verification/promotion later produces a *new* record referencing this
    one.
    """

    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind
    status: CollectionStatus
    subject: Ioc  # discriminated on ``ioc_type`` — the indicator this is about
    provenance: Provenance
    payload: dict[str, str] | None = None  # collected data; bounded; untrusted
    error: str | None = None  # set iff status is FAILURE; bounded
    investigation_id: str | None = None  # opaque passthrough; not identity
    metadata: dict[str, str] = {}  # annotation; bounded; not identity
    # Derived, content-addressed id. Never a caller input — any value passed is
    # overwritten by ``_finalize`` so it is always consistent with the content and
    # recomputed on load (tamper-evident). Defaulted so the field is optional.
    evidence_id: str = ""

    @field_validator("error", "investigation_id")
    @classmethod
    def _check_optional_str(cls, value: str | None) -> str | None:
        if value is not None and len(value) > _MAX_STR:
            raise ValueError(f"value must be at most {_MAX_STR} chars")
        return value

    @field_validator("payload", "metadata")
    @classmethod
    def _check_bounded_map(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return value
        if len(value) > _MAX_META_KEYS:
            raise ValueError(f"map must have at most {_MAX_META_KEYS} keys")
        for key, item in value.items():
            if not 1 <= len(key) <= _MAX_KEY:
                raise ValueError(f"key must be 1..{_MAX_KEY} chars")
            if len(item) > _MAX_VALUE:
                raise ValueError(f"value must be at most {_MAX_VALUE} chars")
        return value

    @model_validator(mode="after")
    def _finalize(self) -> EvidenceRecord:
        # Status/payload/error invariants: a failed or empty collection must not
        # masquerade as carrying collected data, and only a failure carries an error.
        if self.status is CollectionStatus.FAILURE:
            if self.error is None:
                raise ValueError("FAILURE status requires an error")
            if self.payload is not None:
                raise ValueError("FAILURE status must not carry a payload")
        else:
            if self.error is not None:
                raise ValueError("error is only allowed with FAILURE status")
            if self.status is CollectionStatus.EMPTY and self.payload is not None:
                raise ValueError("EMPTY status must not carry a payload")
        # Derive identity from content, overriding anything supplied. object.__set-
        # attr__ is the pydantic-sanctioned way to assign on a frozen model mid-
        # validation; the field is locked immediately after.
        object.__setattr__(self, "evidence_id", self._compute_id())
        return self

    def _compute_id(self) -> str:
        """sha256 over the canonical identity tuple (see module docstring).

        Excludes ``collected_at``, ``investigation_id`` and ``metadata`` so identical
        evidence dedupes across time and investigations. ``sort_keys`` makes the map
        order-independent; the digest is fully deterministic.
        """
        identity = {
            "kind": self.kind.value,
            "subject_type": self.subject.ioc_type,
            "subject": self.subject.normalized,
            "source": self.provenance.source,
            "status": self.status.value,
            "error": self.error,
            "payload": self.payload,
        }
        canonical = json.dumps(
            identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def observation_from_ioc(
    ioc: Ioc,
    *,
    collected_at: datetime,
    source: str = "argus.domain.ioc",
    source_reference: str | None = None,
    tool_run_id: str | None = None,
    investigation_id: str | None = None,
    metadata: dict[str, str] | None = None,
) -> EvidenceRecord:
    """Wrap a deterministic IOC classification as an ARGUS-derived observation.

    The one safe producer of OBSERVATION/SUCCESS evidence: it fixes ``kind``,
    ``status`` and the ARGUS-internal ``source`` so a caller cannot accidentally
    mint an ARGUS fact from external data. ``payload`` stays ``None`` — the
    classification facts already live in the embedded ``subject``. ``collected_at``
    is injected by the caller (the domain never reads the clock).
    """
    return EvidenceRecord(
        kind=EvidenceKind.OBSERVATION,
        status=CollectionStatus.SUCCESS,
        subject=ioc,
        provenance=Provenance(
            source=source,
            collected_at=collected_at,
            source_reference=source_reference,
            tool_run_id=tool_run_id,
        ),
        investigation_id=investigation_id,
        metadata=dict(metadata) if metadata else {},
    )
