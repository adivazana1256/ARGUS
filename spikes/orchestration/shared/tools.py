"""Deterministic mock threat-intelligence tools.

No network, no randomness. Behavior per tool is a scripted sequence supplied by
the scenario, so "fail first then succeed" / "always insufficient" are explicit
and reproducible rather than hidden in global counters.

Tool output is UNTRUSTED (T-TOOL-003): raw payloads may contain adversarial
text; they are returned as data and never interpreted as instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import ToolName, ToolRequest, ToolResult, ToolStatus


@dataclass
class ScriptedResponse:
    """One programmed outcome for a single tool invocation."""

    status: ToolStatus
    payload: dict[str, object] = field(default_factory=dict)
    error: str | None = None
    latency_ms: int = 5


class ScriptedToolProvider:
    """Holds a per-tool response script. Call N returns script entry N; once the
    script is exhausted the last entry repeats (lets "always insufficient" loop
    to the iteration cap without an infinite script).

    State lives on the instance and is reset per test — determinism is explicit.
    """

    def __init__(self, scripts: dict[ToolName, list[ScriptedResponse]]):
        self._scripts = scripts
        self._index: dict[ToolName, int] = {}

    def available_tools(self) -> set[ToolName]:
        return set(self._scripts.keys())

    def run(self, request: ToolRequest) -> ToolResult:
        script = self._scripts.get(request.tool_name)
        if not script:
            # No script => deterministic hard failure (tool genuinely absent).
            return ToolResult(
                request_id=request.request_id,
                tool_name=request.tool_name,
                status=ToolStatus.FAILURE,
                error=f"no mock script for {request.tool_name.value}",
            )
        i = self._index.get(request.tool_name, 0)
        resp = script[min(i, len(script) - 1)]
        self._index[request.tool_name] = i + 1
        return ToolResult(
            request_id=request.request_id,
            tool_name=request.tool_name,
            status=resp.status,
            raw_payload=dict(resp.payload),
            error=resp.error,
            latency_ms=resp.latency_ms,
        )


# Convenience builders for scenario scripts ---------------------------------- #
def malicious_hit(note: str = "listed on blocklist") -> ScriptedResponse:
    return ScriptedResponse(
        status=ToolStatus.SUCCESS,
        payload={"reputation": "malicious", "score": 0.95, "note": note},
    )


def inconclusive_hit(note: str = "no strong signal") -> ScriptedResponse:
    return ScriptedResponse(
        status=ToolStatus.SUCCESS,
        payload={"reputation": "unknown", "score": 0.2, "note": note},
    )


def failure(error: str = "upstream timeout") -> ScriptedResponse:
    return ScriptedResponse(status=ToolStatus.FAILURE, error=error)
