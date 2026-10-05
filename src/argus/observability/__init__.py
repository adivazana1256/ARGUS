"""Observability layer: logging (OTel-ready), cross-cutting.

Cross-cutting: importable by any layer, imports none of them (M0 spec §1.1).
"""

from argus.observability.logging import (
    bind_correlation_id,
    clear_correlation_id,
    configure_logging,
)

__all__ = ["bind_correlation_id", "clear_correlation_id", "configure_logging"]
