"""OpenAI Agents SDK implementation of the ARGUS investigation workflow.

Orchestration (the agent loop, turns, tool dispatch, native tool-approval
interruption and resume) is the SDK's. A deterministic fake model stands in for a
real LLM so the core test suite needs no paid calls. Domain truths, authorization
and limits come from the shared layer.
"""
