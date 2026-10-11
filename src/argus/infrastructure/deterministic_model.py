"""Deterministic investigator model stand-in (M2 Slice 1).

Implements the :class:`~argus.orchestration.models.InvestigatorModel` port with a
pure, reproducible decision policy — no live provider, no network, no randomness
(live model wiring via the Model Gateway is a later slice). It is the model
counterpart of :class:`~argus.infrastructure.mock_threat_intel.MockThreatIntelProvider`:
the offline adapter that lets the agent loop run end to end in tests and local
dev while the authorization/bounds controls stay real.

The decision is genuinely state-driven: it reads collected evidence and the IOC
type to choose the next action, and stops as soon as evidence is decisive. It
reads only structured evidence fields (via ``rules``) — never free-text payload
notes — so adversarial text in a tool response cannot steer it (T-TOOL-003).
"""

from __future__ import annotations

from argus.domain.ipv4 import Ipv4Ioc
from argus.orchestration import rules
from argus.orchestration.models import (
    AgentAction,
    AgentDecision,
    ToolName,
)
from argus.orchestration.state import InvestigationState


class DeterministicInvestigatorModel:
    """Rule-based stand-in for the investigator model.

    Default behavior: reach for the threat-intel lookup matching the IOC type and
    keep collecting until evidence is decisive (the deterministic graph bounds the
    iterations). ``reach_for`` models an investigator that instead reaches for one
    specific tool — used to exercise the sensitive-tool approval and
    unauthorized-tool paths; such a tool is proposed once, then the model
    concludes rather than looping on a one-shot action.
    """

    def __init__(self, reach_for: ToolName | None = None) -> None:
        self._reach_for = reach_for

    def propose_next_action(self, state: InvestigationState) -> AgentDecision:
        if rules.evidence_is_sufficient(state.evidence):
            return AgentDecision(
                action=AgentAction.CONCLUDE, note="decisive evidence collected"
            )
        if self._reach_for is not None:
            already_run = any(
                execution.tool_name is self._reach_for
                for execution in state.tool_executions
            )
            if already_run:
                return AgentDecision(
                    action=AgentAction.CONCLUDE,
                    note="requested action already attempted; nothing further to try",
                )
            return AgentDecision(
                action=AgentAction.PROPOSE_TOOL,
                tool_name=self._reach_for,
                note="reach for the requested tool",
            )
        tool = (
            ToolName.LOOKUP_IP
            if isinstance(state.subject, Ipv4Ioc)
            else ToolName.LOOKUP_DOMAIN
        )
        return AgentDecision(
            action=AgentAction.PROPOSE_TOOL,
            tool_name=tool,
            note="enrich the IOC via threat-intelligence lookup",
        )
