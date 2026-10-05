"""Deterministic ToolPolicy — authorization as ordinary application code,
outside any LLM/model authority (SECURITY T-TOOL-001, T-AI-006, Security Fit).

Order the adapters MUST follow: schema validation -> policy -> (approval) ->
execute. The model may *propose* a ToolRequest; it can never override the verdict
returned here.
"""

from __future__ import annotations

from .models import PolicyDecision, ToolName, ToolRequest


class ToolPolicy:
    """Deny-by-default allowlist with an approval-required subset."""

    def __init__(
        self,
        allowlist: set[ToolName],
        approval_required: set[ToolName] | None = None,
    ):
        self.allowlist = allowlist
        self.approval_required = approval_required or set()

    def evaluate(self, request: ToolRequest) -> PolicyDecision:
        if request.tool_name not in self.allowlist:
            return PolicyDecision.DENY
        if request.tool_name in self.approval_required:
            return PolicyDecision.APPROVAL_REQUIRED
        return PolicyDecision.ALLOW


class SchemaValidationError(ValueError):
    pass


def validate_schema(request: ToolRequest) -> None:
    """Deterministic argument validation (T-TOOL-002). Raises on bad input.

    Minimal for the spike: domain lookups require a non-empty 'target'.
    """
    needs_target = {
        ToolName.LOOKUP_DOMAIN,
        ToolName.LOOKUP_IP,
        ToolName.LOOKUP_HASH,
        ToolName.EXPORT_INTEL,
    }
    if request.tool_name in needs_target:
        target = request.arguments.get("target", "")
        if not target or len(target) > 512:
            raise SchemaValidationError(
                f"{request.tool_name.value} requires 1..512 char 'target'"
            )
