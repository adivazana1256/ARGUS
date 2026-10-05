"""Bounded-execution constants. Single source of truth, imported by both
framework adapters. The *values* are shared; *how* each framework enforces them
is framework-specific orchestration and is what the spike measures.
"""

MAX_INVESTIGATION_ITERATIONS = 3
MAX_TOOL_RETRIES = 2
