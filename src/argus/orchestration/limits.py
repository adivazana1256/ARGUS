"""Bounded-execution constants — the single source of truth for the agent loop.

These values are enforced by deterministic LangGraph edges (``graph.py``), never
by the model. They are the primary control against excessive agency (T-AI-005)
and recursive-loop / cost-abuse DoS (``docs/SECURITY.md`` §13): no path through
the graph can exceed them.
"""

# Maximum number of model-proposed investigation iterations (tool proposals).
MAX_INVESTIGATION_ITERATIONS = 3
# Maximum *additional* retries of a failing tool execution (so a tool runs at
# most ``1 + MAX_TOOL_RETRIES`` times before the loop gives up).
MAX_TOOL_RETRIES = 2
