"""Runnable offline investigation scenario (M1 Investigation Core).

Runs a handful of indicators through the complete deterministic investigation
workflow against the offline :class:`MockThreatIntelProvider` and prints each
verdict-free :class:`InvestigationSummary` as JSON, followed by the raw source
claims each investigation collected (clearly labelled as untrusted claims, not
ARGUS conclusions).

No network, no clock, no randomness: the clock and investigation id are injected,
so every run prints byte-for-byte identical output.

Run it:

    uv run python examples/offline_investigation.py
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from argus.application.investigation import run_investigation, summarize
from argus.infrastructure.mock_threat_intel import MockThreatIntelProvider

# Fixed injected clock so the demo output is reproducible and inspectable.
CLOCK = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

# One indicator per collection scenario the mock provider models.
SCENARIOS = [
    "203.0.113.66",  # malicious claim (FOUND)   -> COMPLETED / SUCCESS
    "malware-c2.example",  # multiple claims (FOUND) -> COMPLETED / SUCCESS
    "8.8.8.8",  # benign claim (FOUND)          -> COMPLETED / SUCCESS
    "198.51.100.23",  # unknown (NOT_FOUND)      -> COMPLETED / NO_FINDINGS
    "192.0.2.200",  # outage (UNAVAILABLE)       -> FAILED / FAILURE
    "malformed.example",  # bad response          -> FAILED / FAILURE
]


def main() -> None:
    providers = [MockThreatIntelProvider()]
    for index, raw in enumerate(SCENARIOS, start=1):
        investigation = run_investigation(
            raw,
            providers,
            investigation_id=f"demo-{index:04d}",
            now=CLOCK,
        )
        summary = summarize(investigation)

        print("=" * 72)
        print(f"INPUT: {raw!r}")
        print(summary.model_dump_json(indent=2))

        claims = [
            record.payload
            for record in investigation.evidence
            if record.payload is not None
        ]
        if claims:
            print("  source claims (untrusted — NOT an ARGUS verdict):")
            print("  " + json.dumps(claims, indent=2).replace("\n", "\n  "))
    print("=" * 72)


if __name__ == "__main__":
    main()
