"""Deterministic fake model for the OpenAI Agents SDK.

Why this exists: the Agents SDK drives everything through a model's tool-calling
decisions. To run the core test suite without paid API calls, we substitute a
model that emits deterministic tool calls. It makes the *domain* decision (call a
tool again vs. finish) using the SHARED rules/limits — it does NOT re-implement
the SDK's loop/turn/tool-dispatch machinery, which the Runner still owns.

This is honest evidence for ADR-002: LangGraph runs model-free trivially; the
SDK requires a stub model to be deterministic (provider coupling).
"""

from __future__ import annotations

import json

from agents import Model, ModelResponse, Usage
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from shared import rules
from shared.limits import MAX_INVESTIGATION_ITERATIONS, MAX_TOOL_RETRIES
from shared.models import InvestigationInput, ToolStatus
from shared.state import InvestigationState


class DeterministicFakeModel(Model):
    """Reads the shared RunBox (mutated by tools between turns) and decides the
    next action via shared domain rules. No network, no paid calls."""

    def __init__(self, box):
        self._box = box
        self._call_seq = 0

    # --- decision logic (domain, via shared rules) ------------------------- #
    def _should_finish(self) -> bool:
        box = self._box
        if box.denied or box.rejected:
            return True
        if not box.tool_results:
            return False  # nothing tried yet -> call the tool
        if box.last_status == ToolStatus.FAILURE:
            # bounded retry, enforced here using the SHARED constant
            return box.attempts >= 1 + MAX_TOOL_RETRIES
        # last call succeeded: ask shared rules whether evidence decides it
        probe = InvestigationState(
            investigation_id=box.inv_id,
            input=InvestigationInput(raw_value=box.raw_ioc, ioc_type=box.ioc_type),
            evidence=box.evidence,
        )
        if rules.evidence_sufficient(probe):
            return True
        # bounded investigation loop, enforced here using the SHARED constant
        return len(box.evidence) >= MAX_INVESTIGATION_ITERATIONS

    # --- Model interface --------------------------------------------------- #
    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    ) -> ModelResponse:
        if self._should_finish():
            msg = ResponseOutputMessage(
                id="final",
                role="assistant",
                status="completed",
                type="message",
                content=[
                    ResponseOutputText(
                        text="investigation concluded", type="output_text", annotations=[]
                    )
                ],
            )
            return ModelResponse(output=[msg], usage=Usage(), response_id=None)

        self._call_seq += 1
        call = ResponseFunctionToolCall(
            call_id=f"call-{self._call_seq}",
            name=self._box.proposed_tool.value,
            arguments=json.dumps({"target": self._box.raw_ioc}),
            type="function_call",
        )
        return ModelResponse(output=[call], usage=Usage(), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError("streaming not used in the spike")

    async def get_retry_advice(self, request):
        return None

    def close(self) -> None:
        pass
