"""Shared, framework-independent domain layer for the orchestration spike.

Contains domain models, deterministic mock tools, ToolPolicy, domain rules,
limits, scenarios and the Orchestrator protocol. Contains NO orchestration
control flow — loops, retries, state transitions and HITL mechanics live in
each framework adapter.
"""
