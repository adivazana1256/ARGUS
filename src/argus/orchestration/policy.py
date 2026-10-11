"""Deterministic authorization — ordinary application code, outside all model
authority (``docs/SECURITY.md`` T-TOOL-001, T-TOOL-002, T-AI-006).

The mandatory order, enforced by ``graph.py``: schema validation -> policy ->
(approval) -> execute. The model may *propose* a :class:`ToolRequest`; it can
never override the verdict returned here, grow the allowlist, or skip approval —
these are plain data structures the model has no handle on.
"""

from __future__ import annotations

from argus.orchestration.models import PolicyDecision, ToolName, ToolRequest

# Tools that require a non-empty 'target' argument before they may run. The
# *length* of every argument is bounded structurally by ``ToolRequest`` itself,
# so this gate owns the per-tool required-field semantics, not the byte bound.
_NEEDS_TARGET = frozenset(
    {ToolName.LOOKUP_IP, ToolName.LOOKUP_DOMAIN, ToolName.EXPORT_INTEL}
)


class SchemaValidationError(ValueError):
    """Raised when a proposed tool's arguments fail typed validation."""


class ToolPolicy:
    """Deny-by-default allowlist with an approval-required subset.

    Frozen at construction from application configuration; nothing at runtime
    (least of all model output) can mutate the allowlist or the approval set."""

    def __init__(
        self,
        allowlist: set[ToolName] | frozenset[ToolName],
        approval_required: set[ToolName] | frozenset[ToolName] | None = None,
    ) -> None:
        self._allowlist = frozenset(allowlist)
        self._approval_required = frozenset(approval_required or frozenset())

    @property
    def allowlist(self) -> frozenset[ToolName]:
        return self._allowlist

    @property
    def approval_required(self) -> frozenset[ToolName]:
        return self._approval_required

    def evaluate(self, request: ToolRequest) -> PolicyDecision:
        if request.tool_name not in self._allowlist:
            return PolicyDecision.DENY
        if request.tool_name in self._approval_required:
            return PolicyDecision.APPROVAL_REQUIRED
        return PolicyDecision.ALLOW


def validate_schema(request: ToolRequest) -> None:
    """Typed, deterministic argument validation (T-TOOL-002). Raises on bad input.

    Runs *before* the policy check so a malformed request is rejected regardless
    of whether its tool is allowlisted.
    """
    if request.tool_name in _NEEDS_TARGET and not request.arguments.get("target"):
        raise SchemaValidationError(
            f"{request.tool_name.value} requires a non-empty 'target'"
        )
