"""Shared pytest fixtures. The `orchestrator` fixture parametrizes every test
over BOTH framework adapters, so each scenario is asserted identically against
LangGraph and the OpenAI Agents SDK."""

from __future__ import annotations

import warnings

import pytest

# LangGraph's checkpointer warns when (de)serializing our custom pydantic types.
# Harmless for the spike; noted in RESULTS.md. Silence to keep output readable.
warnings.filterwarnings("ignore", message="Deserializing unregistered type.*")

from langgraph_impl.adapter import LangGraphOrchestrator
from openai_agents.adapter import OpenAIAgentsOrchestrator


@pytest.fixture(
    params=[LangGraphOrchestrator, OpenAIAgentsOrchestrator],
    ids=["langgraph", "openai_agents"],
)
def orchestrator(request):
    return request.param()
