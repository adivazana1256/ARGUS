"""Tool execution — the authorized bridge from a proposed action to real work.

Execution runs *only after* ``graph.py`` has cleared the request through schema
validation, policy and (if required) human approval. Collection tools go through
the existing M1 :func:`~argus.application.collection.collect` contract, so every
produced record is a real, provenance-bearing ``EvidenceRecord`` — the agent
proposes, but M1 creates evidence. Tool output stays untrusted data (T-TOOL-003):
it is stored, never interpreted here.
"""

from __future__ import annotations

from datetime import datetime

from argus.application.collection import (
    CollectionOutcome,
    ThreatIntelProvider,
    collect,
)
from argus.domain.evidence import EvidenceRecord
from argus.domain.ioc import Ioc
from argus.orchestration.models import (
    ToolExecution,
    ToolName,
    ToolRequest,
    ToolStatus,
)

# Tools whose execution is a threat-intel lookup over the collection contract.
_LOOKUP_TOOLS = frozenset({ToolName.LOOKUP_IP, ToolName.LOOKUP_DOMAIN})


class ToolExecutor:
    """Runs an authorized :class:`ToolRequest`. Providers and the clock are
    injected (determinism); nothing here reads a wall clock or the network."""

    def __init__(self, providers: list[ThreatIntelProvider], *, now: datetime) -> None:
        self._providers = providers
        self._now = now

    @property
    def now(self) -> datetime:
        """The injected collection clock, reused as the investigation clock so
        tool executions and audit events share one deterministic timestamp."""
        return self._now

    def execute(
        self,
        request: ToolRequest,
        subject: Ioc,
        *,
        attempt: int,
        investigation_id: str,
    ) -> tuple[ToolExecution, list[EvidenceRecord]]:
        """Execute one authorized request, returning the audit record and any
        evidence it produced."""
        if request.tool_name in _LOOKUP_TOOLS:
            return self._run_lookup(
                request, subject, attempt=attempt, investigation_id=investigation_id
            )
        # EXPORT_INTEL: a sensitive action, not a collection. It produces no
        # evidence; reaching here means it was already approved and allowlisted.
        return (
            ToolExecution(
                request_id=request.request_id,
                tool_name=request.tool_name,
                status=ToolStatus.SUCCESS,
                attempt=attempt,
                at=self._now,
            ),
            [],
        )

    def _run_lookup(
        self,
        request: ToolRequest,
        subject: Ioc,
        *,
        attempt: int,
        investigation_id: str,
    ) -> tuple[ToolExecution, list[EvidenceRecord]]:
        result = collect(
            subject,
            self._providers,
            collected_at=self._now,
            investigation_id=investigation_id,
        )
        evidence = list(result.evidence)
        # FAILURE means nobody could look / every attempt failed — the only
        # outcome worth a bounded retry. Findings, absence and partials are all
        # successful *collections* even if not decisive.
        status = (
            ToolStatus.FAILURE
            if result.outcome is CollectionOutcome.FAILURE
            else ToolStatus.SUCCESS
        )
        error = None if status is ToolStatus.SUCCESS else "collection failed"
        execution = ToolExecution(
            request_id=request.request_id,
            tool_name=request.tool_name,
            status=status,
            attempt=attempt,
            error=error,
            evidence_ids=tuple(record.evidence_id for record in evidence),
            at=self._now,
        )
        return execution, evidence
