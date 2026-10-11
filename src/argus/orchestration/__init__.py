"""ARGUS AI Orchestration Layer (M2 — Agentic Investigator).

Wraps the deterministic M1 investigation core in a *bounded, evidence-driven
agent loop* (``docs/ARCHITECTURE.md`` §5, ADR-002). A model proposes the next
action; deterministic controls — ``ToolPolicy``, typed schema validation,
iteration/retry bounds and an enumerated termination reason — authorize and bound
it. Evidence is created only through the existing M1 collection path, so every
record keeps real provenance and a model-asserted value never becomes evidence.

Layer rules (enforced by ``tests/architecture/``): orchestration may import
``domain`` and ``application`` (and LangGraph); ``domain``/``application`` must
never import orchestration; orchestration imports neither ``api`` nor
``infrastructure`` — the model and provider adapters are injected at the
composition root. LangGraph is confined to :mod:`argus.orchestration.graph` and
:mod:`argus.orchestration.orchestrator`; the rest of the layer is
framework-agnostic plain code.
"""

from argus.orchestration.limits import (
    MAX_INVESTIGATION_ITERATIONS,
    MAX_TOOL_RETRIES,
)
from argus.orchestration.models import (
    AgentAction,
    AgentDecision,
    ApprovalDecision,
    InvestigatorModel,
    OrchestrationStatus,
    PolicyDecision,
    TerminationReason,
    ToolExecution,
    ToolName,
    ToolRequest,
    ToolStatus,
)
from argus.orchestration.orchestrator import (
    InvestigationOrchestrator,
    LangGraphOrchestrator,
    RunOutcome,
)
from argus.orchestration.policy import (
    SchemaValidationError,
    ToolPolicy,
    validate_schema,
)
from argus.orchestration.state import InvestigationState
from argus.orchestration.tools import ToolExecutor

__all__ = [
    "MAX_INVESTIGATION_ITERATIONS",
    "MAX_TOOL_RETRIES",
    "AgentAction",
    "AgentDecision",
    "ApprovalDecision",
    "InvestigationOrchestrator",
    "InvestigationState",
    "InvestigatorModel",
    "LangGraphOrchestrator",
    "OrchestrationStatus",
    "PolicyDecision",
    "RunOutcome",
    "SchemaValidationError",
    "TerminationReason",
    "ToolExecution",
    "ToolExecutor",
    "ToolName",
    "ToolPolicy",
    "ToolRequest",
    "ToolStatus",
    "validate_schema",
]
