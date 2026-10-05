"""LangGraph implementation of the ARGUS investigation workflow.

Orchestration (state transitions, the bounded loop, retry edges, HITL interrupt/
resume) is expressed with LangGraph primitives here. Domain truths, authorization
and limits come from the shared layer.
"""
