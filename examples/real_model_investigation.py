"""Manual smoke: one bounded investigation driven by the REAL LLM (M2 Slice 2).

Unlike ``offline_investigation.py``, this makes a real, paid Anthropic call per
decision, so it is a manual demo — never part of ``make test`` / CI (it lives in
``examples/``, outside ``testpaths``, and no test imports it). It still runs the
threat-intel collection against the offline mock provider: only the *reasoning*
step is real. Authorization, bounds and evidence stay deterministic — the model
only proposes.

Prerequisites:

    export ARGUS_ANTHROPIC_API_KEY=sk-ant-...   # your key; never commit it
    # optional: export ARGUS_LLM_MODEL=claude-opus-4-8

Run it:

    uv run python examples/real_model_investigation.py 203.0.113.66

The investigation clock is injected so tool executions and the audit timeline are
reproducible; the model's decisions are not (that is the point of the smoke test).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from argus.config import load_settings
from argus.domain.ioc import parse_ioc
from argus.infrastructure.anthropic_investigator import AnthropicInvestigatorModel
from argus.infrastructure.mock_threat_intel import MockThreatIntelProvider
from argus.orchestration.models import ToolName
from argus.orchestration.orchestrator import LangGraphOrchestrator
from argus.orchestration.policy import ToolPolicy
from argus.orchestration.tools import ToolExecutor

CLOCK = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def main(raw_ioc: str) -> None:
    settings = load_settings()  # reads ARGUS_ANTHROPIC_API_KEY from env / .env
    model = AnthropicInvestigatorModel.from_settings(settings)

    orchestrator = LangGraphOrchestrator(
        model,
        # Deny-by-default: only the offline lookups are allowed; the sensitive
        # export_intel tool is deliberately NOT allowlisted, so even if the real
        # model proposes it, it is denied — never executed.
        ToolPolicy(allowlist=frozenset({ToolName.LOOKUP_IP, ToolName.LOOKUP_DOMAIN})),
        ToolExecutor([MockThreatIntelProvider()], now=CLOCK),
    )

    outcome = orchestrator.run(parse_ioc(raw_ioc), investigation_id="smoke-0001")
    state = outcome.state

    print("=" * 72)
    print(f"INPUT: {raw_ioc!r}  model={settings.llm_model}")
    print(f"status={state.status.value}  stop_reason={state.termination_reason}")
    print("timeline:")
    for event in state.events:
        print(f"  - {event.step}: {event.detail}")
    print(f"tool executions: {[e.tool_name.value for e in state.tool_executions]}")
    print("=" * 72)


if __name__ == "__main__":
    ioc = sys.argv[1] if len(sys.argv) > 1 else "203.0.113.66"
    main(ioc)
