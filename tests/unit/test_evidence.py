"""Tests for the deterministic Evidence Core (``argus.domain.evidence``).

Scope: the evidence record itself — provenance preservation, deterministic
content-addressed identity/dedup, the fact/claim boundary, collection-outcome
invariants, serialization round-trip and the untrusted-metadata bounds. IOC
parsing/classification semantics are owned by ``test_ipv4.py`` / ``test_domain.py``
and are not re-tested here (cyber-domain-review; ``docs/EVALUATION.md`` §4).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from argus.domain.evidence import (
    CollectionStatus,
    EvidenceKind,
    EvidenceRecord,
    Provenance,
    observation_from_ioc,
)
from argus.domain.ioc import Ioc, parse_ioc
from argus.domain.ipv4 import Ipv4Ioc

# A fixed, injected collection time — the domain never reads the wall-clock.
AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
LATER = datetime(2026, 6, 7, 8, 9, 10, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# observation_from_ioc: the one safe producer of ARGUS-derived facts.
# --------------------------------------------------------------------------- #


def test_observation_wraps_ioc_as_argus_fact() -> None:
    ev = observation_from_ioc(parse_ioc("8.8.8.8"), collected_at=AT)
    assert ev.kind is EvidenceKind.OBSERVATION
    assert ev.status is CollectionStatus.SUCCESS
    assert ev.provenance.source == "argus.domain.ioc"
    assert ev.payload is None  # the facts live in the subject, not a payload
    assert isinstance(ev.subject, Ipv4Ioc)
    assert ev.subject.normalized == "8.8.8.8"


def test_provenance_preserves_raw_observable() -> None:
    # The domain IOC diverges raw vs normalized; evidence must not lose the raw
    # value. It is carried inside the embedded subject, not discarded.
    ev = observation_from_ioc(parse_ioc("Example.COM."), collected_at=AT)
    assert ev.subject.raw == "Example.COM."
    assert ev.subject.normalized == "example.com"


def test_injected_collection_time_is_recorded_as_utc() -> None:
    ev = observation_from_ioc(parse_ioc("1.1.1.1"), collected_at=AT)
    assert ev.provenance.collected_at == AT


# --------------------------------------------------------------------------- #
# Deterministic, content-addressed identity + dedup semantics (D6).
# --------------------------------------------------------------------------- #


def test_identity_is_deterministic() -> None:
    a = observation_from_ioc(parse_ioc("8.8.8.8"), collected_at=AT)
    b = observation_from_ioc(parse_ioc("8.8.8.8"), collected_at=AT)
    assert a.evidence_id == b.evidence_id
    assert len(a.evidence_id) == 64  # sha256 hexdigest


def test_identity_excludes_collection_time_and_investigation() -> None:
    # The same fact collected at a different time, in a different investigation,
    # with different annotation metadata dedupes to the same evidence_id.
    a = observation_from_ioc(
        parse_ioc("8.8.8.8"),
        collected_at=AT,
        investigation_id="inv-1",
        metadata={"note": "first"},
    )
    b = observation_from_ioc(
        parse_ioc("8.8.8.8"),
        collected_at=LATER,
        investigation_id="inv-2",
        metadata={"note": "second"},
    )
    assert a.evidence_id == b.evidence_id


def test_identity_depends_on_subject() -> None:
    a = observation_from_ioc(parse_ioc("8.8.8.8"), collected_at=AT)
    b = observation_from_ioc(parse_ioc("1.1.1.1"), collected_at=AT)
    assert a.evidence_id != b.evidence_id


def test_identity_depends_on_source() -> None:
    a = observation_from_ioc(parse_ioc("8.8.8.8"), collected_at=AT, source="src-a")
    b = observation_from_ioc(parse_ioc("8.8.8.8"), collected_at=AT, source="src-b")
    assert a.evidence_id != b.evidence_id


def test_identity_depends_on_payload() -> None:
    subject = parse_ioc("8.8.8.8")
    prov = Provenance(source="feed", collected_at=AT)
    a = _claim(subject, prov, {"reputation": "malicious"})
    b = _claim(subject, prov, {"reputation": "benign"})
    assert a.evidence_id != b.evidence_id


def test_payload_key_order_does_not_change_identity() -> None:
    subject = parse_ioc("8.8.8.8")
    prov = Provenance(source="feed", collected_at=AT)
    a = _claim(subject, prov, {"a": "1", "b": "2"})
    b = _claim(subject, prov, {"b": "2", "a": "1"})
    assert a.evidence_id == b.evidence_id


def test_claim_and_observation_are_distinct_evidence() -> None:
    # The fact/claim boundary is part of identity: an external claim can never
    # collapse onto an ARGUS observation about the same subject (T-AI-004).
    subject = parse_ioc("8.8.8.8")
    prov = Provenance(source="argus.domain.ioc", collected_at=AT)
    observation = observation_from_ioc(subject, collected_at=AT)
    claim = EvidenceRecord(
        kind=EvidenceKind.CLAIM,
        status=CollectionStatus.SUCCESS,
        subject=subject,
        provenance=prov,
    )
    assert observation.kind is EvidenceKind.OBSERVATION
    assert claim.kind is EvidenceKind.CLAIM
    assert observation.evidence_id != claim.evidence_id


# --------------------------------------------------------------------------- #
# Collection-time validation: naive rejected, aware normalized to UTC.
# --------------------------------------------------------------------------- #


def test_naive_collection_time_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Provenance(source="feed", collected_at=datetime(2026, 1, 1, 0, 0, 0))


def test_aware_non_utc_time_is_normalized_to_utc() -> None:
    eastern = timezone(timedelta(hours=-5))
    prov = Provenance(
        source="feed", collected_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=eastern)
    )
    assert prov.collected_at == datetime(2026, 1, 1, 5, 0, 0, tzinfo=UTC)
    assert prov.collected_at.tzinfo == UTC


# --------------------------------------------------------------------------- #
# Immutability + serialization round-trip + tamper-evidence.
# --------------------------------------------------------------------------- #


def test_record_is_frozen() -> None:
    ev = observation_from_ioc(parse_ioc("8.8.8.8"), collected_at=AT)
    with pytest.raises(ValidationError):
        ev.status = CollectionStatus.FAILURE


def test_provenance_is_frozen() -> None:
    ev = observation_from_ioc(parse_ioc("8.8.8.8"), collected_at=AT)
    with pytest.raises(ValidationError):
        ev.provenance.source = "attacker"


def test_json_round_trip_preserves_everything() -> None:
    original = _claim(
        parse_ioc("evil.example-feed.com"),
        Provenance(source="feed", collected_at=AT, source_reference="ref-9"),
        {"reputation": "malicious", "first_seen": "2026-01-01"},
    )
    reloaded = EvidenceRecord.model_validate_json(original.model_dump_json())
    assert reloaded == original
    assert reloaded.evidence_id == original.evidence_id
    # The discriminated subject reloads as the correct concrete IOC type.
    assert reloaded.subject.ioc_type == original.subject.ioc_type


def test_identity_is_recomputed_on_load_ignoring_supplied_value() -> None:
    # evidence_id is derived, never trusted from input: a tampered id is discarded
    # and recomputed from content on load.
    ev = observation_from_ioc(parse_ioc("8.8.8.8"), collected_at=AT)
    payload = ev.model_dump()
    payload["evidence_id"] = "0" * 64  # attacker-supplied bogus id
    reloaded = EvidenceRecord.model_validate(payload)
    assert reloaded.evidence_id == ev.evidence_id


def test_tampering_payload_changes_identity() -> None:
    original = _claim(
        parse_ioc("8.8.8.8"),
        Provenance(source="feed", collected_at=AT),
        {"reputation": "malicious"},
    )
    tampered = original.model_dump()
    tampered["payload"] = {"reputation": "benign"}
    reloaded = EvidenceRecord.model_validate(tampered)
    assert reloaded.evidence_id != original.evidence_id


# --------------------------------------------------------------------------- #
# Collection-outcome invariants: a failed/empty collection cannot masquerade.
# --------------------------------------------------------------------------- #


def test_failure_requires_error() -> None:
    with pytest.raises(ValidationError, match="FAILURE status requires an error"):
        EvidenceRecord(
            kind=EvidenceKind.CLAIM,
            status=CollectionStatus.FAILURE,
            subject=parse_ioc("8.8.8.8"),
            provenance=Provenance(source="feed", collected_at=AT),
        )


def test_failure_must_not_carry_payload() -> None:
    with pytest.raises(ValidationError, match="must not carry a payload"):
        EvidenceRecord(
            kind=EvidenceKind.CLAIM,
            status=CollectionStatus.FAILURE,
            subject=parse_ioc("8.8.8.8"),
            provenance=Provenance(source="feed", collected_at=AT),
            error="timeout",
            payload={"k": "v"},
        )


def test_error_only_allowed_with_failure() -> None:
    with pytest.raises(ValidationError, match="only allowed with FAILURE"):
        EvidenceRecord(
            kind=EvidenceKind.CLAIM,
            status=CollectionStatus.SUCCESS,
            subject=parse_ioc("8.8.8.8"),
            provenance=Provenance(source="feed", collected_at=AT),
            error="should not be here",
        )


def test_empty_must_not_carry_payload() -> None:
    with pytest.raises(ValidationError, match="EMPTY status must not carry a payload"):
        EvidenceRecord(
            kind=EvidenceKind.CLAIM,
            status=CollectionStatus.EMPTY,
            subject=parse_ioc("8.8.8.8"),
            provenance=Provenance(source="feed", collected_at=AT),
            payload={"k": "v"},
        )


def test_failure_record_is_valid_and_provenance_bearing() -> None:
    ev = EvidenceRecord(
        kind=EvidenceKind.CLAIM,
        status=CollectionStatus.FAILURE,
        subject=parse_ioc("8.8.8.8"),
        provenance=Provenance(source="feed", collected_at=AT),
        error="connection timed out",
    )
    assert ev.status is CollectionStatus.FAILURE
    assert ev.payload is None
    assert ev.provenance.source == "feed"  # a failure is still attributable


def test_empty_record_is_valid() -> None:
    ev = EvidenceRecord(
        kind=EvidenceKind.CLAIM,
        status=CollectionStatus.EMPTY,
        subject=parse_ioc("8.8.8.8"),
        provenance=Provenance(source="feed", collected_at=AT),
    )
    assert ev.status is CollectionStatus.EMPTY
    assert ev.payload is None


# --------------------------------------------------------------------------- #
# Untrusted-input hardening: oversized / malformed source metadata is rejected.
# --------------------------------------------------------------------------- #


def test_source_must_not_be_empty() -> None:
    with pytest.raises(ValidationError, match="source must be"):
        Provenance(source="", collected_at=AT)


def test_oversized_source_is_rejected() -> None:
    with pytest.raises(ValidationError, match="source must be"):
        Provenance(source="x" * 513, collected_at=AT)


def test_oversized_optional_provenance_string_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at most 512"):
        Provenance(source="feed", collected_at=AT, source_reference="r" * 513)


def test_too_many_metadata_keys_rejected() -> None:
    with pytest.raises(ValidationError, match="at most 32 keys"):
        observation_from_ioc(
            parse_ioc("8.8.8.8"),
            collected_at=AT,
            metadata={str(i): "v" for i in range(33)},
        )


def test_oversized_metadata_value_rejected() -> None:
    with pytest.raises(ValidationError, match="at most 1024"):
        observation_from_ioc(
            parse_ioc("8.8.8.8"), collected_at=AT, metadata={"k": "v" * 1025}
        )


def test_oversized_metadata_key_rejected() -> None:
    with pytest.raises(ValidationError, match="1..128 chars"):
        observation_from_ioc(
            parse_ioc("8.8.8.8"), collected_at=AT, metadata={"k" * 129: "v"}
        )


def test_oversized_payload_rejected() -> None:
    with pytest.raises(ValidationError, match="at most 1024"):
        _claim(
            parse_ioc("8.8.8.8"),
            Provenance(source="feed", collected_at=AT),
            {"k": "v" * 1025},
        )


def test_oversized_investigation_id_rejected() -> None:
    with pytest.raises(ValidationError, match="at most 512"):
        observation_from_ioc(
            parse_ioc("8.8.8.8"), collected_at=AT, investigation_id="i" * 513
        )


def test_oversized_error_rejected() -> None:
    with pytest.raises(ValidationError, match="at most 512"):
        EvidenceRecord(
            kind=EvidenceKind.CLAIM,
            status=CollectionStatus.FAILURE,
            subject=parse_ioc("8.8.8.8"),
            provenance=Provenance(source="feed", collected_at=AT),
            error="e" * 513,
        )


def test_bounds_edges_are_accepted() -> None:
    # Exactly at the limits is allowed; only strictly over is rejected.
    ev = observation_from_ioc(
        parse_ioc("8.8.8.8"),
        collected_at=AT,
        metadata={"k" * 128: "v" * 1024, **{str(i): "x" for i in range(31)}},
    )
    assert len(ev.metadata) == 32


def _claim(
    subject: Ioc, provenance: Provenance, payload: dict[str, str]
) -> EvidenceRecord:
    """Build a SUCCESS external CLAIM record (test helper, no production producer)."""
    return EvidenceRecord(
        kind=EvidenceKind.CLAIM,
        status=CollectionStatus.SUCCESS,
        subject=subject,
        provenance=provenance,
        payload=payload,
    )
