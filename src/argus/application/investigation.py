"""Deterministic investigation lifecycle (M1 Investigation Core).

Connects the existing M1 slices into one inspectable workflow:

    raw observable
      -> parse_ioc            (validation / normalization)
      -> create_investigation (CREATED)
      -> collect              (threat-intel collection, existing contract)
      -> with_evidence        (evidence association)
      -> transition_to        (lifecycle update)
      -> summarize            (deterministic, verdict-free summary)

Application layer: imports ``domain`` and the sibling ``collection`` use-case
only, never ``infrastructure`` or ``api`` (``docs/ARCHITECTURE.md`` §1.1, §4;
enforced by ``tests/architecture/``). Providers are injected as the
:class:`ThreatIntelProvider` port, so the offline mock and a future real adapter
are interchangeable without this module changing.

Design decisions worth knowing before changing this (approved architecture gate):

* **An investigation is not a verdict.** The terminal :class:`InvestigationStatus`
  describes the *lifecycle* outcome (did collection complete, partially complete,
  or fail), never a malicious/benign judgement. A provider's "malicious" stays a
  CLAIM inside the evidence payload; nothing here aggregates claims into a
  conclusion, a score, or an attribution (``docs/SECURITY.md`` §6;
  ``docs/ARCHITECTURE.md`` §7).

* **Absence is never benign.** ``NO_FINDINGS`` maps to ``COMPLETED`` because the
  lifecycle finished cleanly — but the summary records an explicit limitation that
  absence of findings is not evidence of benignness. "No provider could even look"
  (unsupported IOC) is a ``FAILURE`` collection outcome and maps to ``FAILED``,
  distinct from "nobody found anything".

* **Identity and time are injected, never generated here.** ``investigation_id``
  and the clock are supplied by the caller (mirroring the injected clock the
  evidence/collection layers already use). The domain reads no wall clock and
  mints no randomness, so a run is byte-for-byte reproducible.

* **Evidence is associated, never mutated or fabricated.** Association validates
  that each record is about this investigation's exact subject and (if stamped)
  carries this investigation's id, dedupes by the content-addressed
  ``evidence_id``, and preserves provenance verbatim. A cross-IOC or cross-
  investigation record is rejected, not silently attached. Collection failures are
  carried as their own FAILURE evidence records — never dropped, never replaced
  with invented data.

* **Transitions are explicit and total.** The state machine rejects any transition
  not in :data:`_ALLOWED_TRANSITIONS`; terminal states accept none. Invalid
  transitions raise rather than silently no-op.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from argus.application.collection import (
    CollectionOutcome,
    CollectionResult,
    ThreatIntelProvider,
    collect,
)
from argus.domain.evidence import EvidenceRecord
from argus.domain.ioc import Ioc, parse_ioc

# Bounds the caller-supplied investigation id. Matched to the evidence layer's
# string bound so an id that ``collect`` stamps onto a record can never be
# rejected downstream.
_MAX_ID = 512


class InvalidTransitionError(ValueError):
    """Raised when a lifecycle transition is not permitted from the current state."""


class EvidenceAssociationError(ValueError):
    """Raised when evidence cannot be associated with an investigation.

    Covers a subject that does not match the investigation's IOC (cross-IOC
    mismatch) and a record stamped with a different investigation's id.
    """


class InvestigationStatus(StrEnum):
    """Lifecycle state of an investigation. Describes workflow, not threat level."""

    CREATED = "created"  # investigation opened over a validated IOC; no collection yet
    COLLECTING = "collecting"  # collection in progress
    COMPLETED = "completed"  # collection finished (findings or none) — NOT "benign"
    PARTIAL = "partial"  # collection finished but at least one provider failed
    FAILED = "failed"  # collection failed, or no provider could look


# source state -> states reachable from it. Terminal states map to the empty set.
_ALLOWED_TRANSITIONS: dict[InvestigationStatus, frozenset[InvestigationStatus]] = {
    InvestigationStatus.CREATED: frozenset({InvestigationStatus.COLLECTING}),
    InvestigationStatus.COLLECTING: frozenset(
        {
            InvestigationStatus.COMPLETED,
            InvestigationStatus.PARTIAL,
            InvestigationStatus.FAILED,
        }
    ),
    InvestigationStatus.COMPLETED: frozenset(),
    InvestigationStatus.PARTIAL: frozenset(),
    InvestigationStatus.FAILED: frozenset(),
}

# Collection outcome -> the terminal lifecycle state it drives. Exhaustive over
# CollectionOutcome. NO_FINDINGS completes cleanly (absence is flagged as a
# limitation in the summary, never as a benign verdict).
_OUTCOME_STATUS: dict[CollectionOutcome, InvestigationStatus] = {
    CollectionOutcome.SUCCESS: InvestigationStatus.COMPLETED,
    CollectionOutcome.NO_FINDINGS: InvestigationStatus.COMPLETED,
    CollectionOutcome.PARTIAL: InvestigationStatus.PARTIAL,
    CollectionOutcome.FAILURE: InvestigationStatus.FAILED,
}

# Explicit, deterministic limitation strings surfaced in the summary. They exist
# so a reader is never left to infer a verdict from silence.
_ABSENCE_NOT_BENIGN = (
    "No provider returned findings; absence of findings is not evidence of benignness."
)
_PARTIAL_WARN = (
    "At least one provider failed; results are partial and may be incomplete."
)
_NO_CAPABLE_PROVIDER = (
    "No configured provider supports this IOC type; no intelligence was collected."
)
_ALL_PROVIDERS_FAILED = "All providers failed; no intelligence could be collected."
_CLAIMS_NOT_VERDICTS = (
    "All provider findings are unverified source claims, not ARGUS-verified verdicts."
)


def _as_utc(value: datetime) -> datetime:
    """Require a timezone-aware timestamp and canonicalize it to UTC.

    Mirrors the evidence layer: naive datetimes are ambiguous across hosts and
    non-deterministic, so they are rejected rather than assumed to be in any zone.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class Investigation(BaseModel):
    """One immutable snapshot of an investigation's lifecycle.

    Frozen: transitions and evidence association return a *new* Investigation, the
    prior snapshot is never mutated. ``outcome`` and ``providers_queried`` are
    populated once collection has run.
    """

    model_config = ConfigDict(frozen=True)

    investigation_id: str
    subject: Ioc  # the validated, typed IOC this investigation is about
    status: InvestigationStatus
    created_at: datetime  # tz-aware, normalized to UTC; injected
    updated_at: datetime  # tz-aware, normalized to UTC; injected, bumped per change
    evidence: tuple[EvidenceRecord, ...] = ()
    outcome: CollectionOutcome | None = None  # None until collection has run
    providers_queried: tuple[str, ...] = ()

    @field_validator("investigation_id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        if not value or len(value) > _MAX_ID:
            raise ValueError(f"investigation_id must be 1..{_MAX_ID} chars")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def _require_aware_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)

    def transition_to(
        self,
        new_status: InvestigationStatus,
        *,
        now: datetime,
        outcome: CollectionOutcome | None = None,
        providers_queried: tuple[str, ...] | None = None,
    ) -> Investigation:
        """Return a new snapshot in ``new_status``; reject an invalid transition.

        ``outcome``/``providers_queried`` are recorded when supplied (on the
        transition out of COLLECTING). A transition not permitted from the current
        state raises :class:`InvalidTransitionError`.
        """
        if new_status not in _ALLOWED_TRANSITIONS[self.status]:
            raise InvalidTransitionError(
                f"cannot transition {self.status.value} -> {new_status.value}"
            )
        update: dict[str, object] = {
            "status": new_status,
            "updated_at": _as_utc(now),
        }
        if outcome is not None:
            update["outcome"] = outcome
        if providers_queried is not None:
            update["providers_queried"] = providers_queried
        return self.model_copy(update=update)

    def with_evidence(
        self, records: Iterable[EvidenceRecord], *, now: datetime
    ) -> Investigation:
        """Return a new snapshot with ``records`` associated (validated, deduped).

        Each record must be about this investigation's exact subject and, if it
        carries an ``investigation_id``, must carry *this* one. Records are never
        mutated; a record whose ``evidence_id`` is already present is skipped
        (dedupe), preserving the first occurrence and its provenance.
        """
        seen = {record.evidence_id for record in self.evidence}
        associated = list(self.evidence)
        for record in records:
            self._check_associable(record)
            if record.evidence_id in seen:
                continue  # content-addressed dedupe; keep the existing record
            seen.add(record.evidence_id)
            associated.append(record)
        return self.model_copy(
            update={"evidence": tuple(associated), "updated_at": _as_utc(now)}
        )

    def _check_associable(self, record: EvidenceRecord) -> None:
        subject = record.subject
        if (
            subject.ioc_type != self.subject.ioc_type
            or subject.normalized != self.subject.normalized
        ):
            raise EvidenceAssociationError(
                "evidence subject does not match the investigation subject"
            )
        if (
            record.investigation_id is not None
            and record.investigation_id != self.investigation_id
        ):
            raise EvidenceAssociationError(
                "evidence belongs to a different investigation"
            )


class InvestigationSummary(BaseModel):
    """Structured, deterministic, verdict-free summary of an investigation.

    Carries identity, lifecycle status, evidence references and the collection
    outcome, plus an explicit list of limitations. It deliberately exposes no
    aggregated verdict, score, or attribution — claimed verdicts remain inside the
    referenced evidence as source claims.
    """

    model_config = ConfigDict(frozen=True)

    investigation_id: str
    ioc_type: str
    normalized_value: str
    status: InvestigationStatus
    outcome: CollectionOutcome | None
    evidence_count: int
    evidence_ids: tuple[str, ...]
    providers_queried: tuple[str, ...]
    limitations: tuple[str, ...]


def create_investigation(
    subject: Ioc, *, investigation_id: str, now: datetime
) -> Investigation:
    """Open a new investigation in the CREATED state over a validated IOC."""
    return Investigation(
        investigation_id=investigation_id,
        subject=subject,
        status=InvestigationStatus.CREATED,
        created_at=now,
        updated_at=now,
    )


def summarize(investigation: Investigation) -> InvestigationSummary:
    """Produce the deterministic summary for an investigation snapshot."""
    return InvestigationSummary(
        investigation_id=investigation.investigation_id,
        ioc_type=investigation.subject.ioc_type,
        normalized_value=investigation.subject.normalized,
        status=investigation.status,
        outcome=investigation.outcome,
        evidence_count=len(investigation.evidence),
        evidence_ids=tuple(record.evidence_id for record in investigation.evidence),
        providers_queried=investigation.providers_queried,
        limitations=_limitations(investigation),
    )


def _limitations(investigation: Investigation) -> tuple[str, ...]:
    """Derive explicit limitation strings from the lifecycle outcome.

    Deterministic and order-stable: the reader never has to infer a conclusion
    from missing data.
    """
    limitations: list[str] = []
    outcome = investigation.outcome
    if outcome is CollectionOutcome.NO_FINDINGS:
        limitations.append(_ABSENCE_NOT_BENIGN)
    elif outcome is CollectionOutcome.PARTIAL:
        limitations.append(_PARTIAL_WARN)
    elif outcome is CollectionOutcome.FAILURE:
        limitations.append(
            _NO_CAPABLE_PROVIDER
            if not investigation.providers_queried
            else _ALL_PROVIDERS_FAILED
        )
    # Any stored payload is a source claim; say so plainly so a "malicious" claim
    # is never read as an ARGUS verdict.
    if any(record.payload for record in investigation.evidence):
        limitations.append(_CLAIMS_NOT_VERDICTS)
    return tuple(limitations)


def run_investigation(
    raw: str,
    providers: Sequence[ThreatIntelProvider],
    *,
    investigation_id: str,
    now: datetime,
) -> Investigation:
    """Run one complete deterministic investigation over a raw observable.

    Parses and validates the observable (a malformed value raises
    :class:`~argus.domain.ioc.IocValidationError` and *no* investigation is
    opened), opens the investigation, collects threat intel from every capable
    provider via the existing :func:`~argus.application.collection.collect`
    contract, associates the resulting evidence, and transitions to the terminal
    state implied by the collection outcome. The clock and id are injected, so the
    run is fully reproducible.
    """
    subject = parse_ioc(raw)
    investigation = create_investigation(
        subject, investigation_id=investigation_id, now=now
    )
    investigation = investigation.transition_to(InvestigationStatus.COLLECTING, now=now)
    result: CollectionResult = collect(
        subject, providers, collected_at=now, investigation_id=investigation_id
    )
    investigation = investigation.with_evidence(result.evidence, now=now)
    return investigation.transition_to(
        _OUTCOME_STATUS[result.outcome],
        now=now,
        outcome=result.outcome,
        providers_queried=result.providers_queried,
    )
