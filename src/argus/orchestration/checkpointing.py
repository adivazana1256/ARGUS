"""Checkpointer construction with an explicit type allowlist.

ADR-002 requires registering ARGUS's custom Pydantic/enum types with the
LangGraph checkpointer (``allowed_msgpack_modules``) rather than relying on the
permissive default that deserializes any type with a warning. Registering an
explicit allowlist is the secure posture: a persisted checkpoint can only
rehydrate ARGUS's own known types, closing the deserialization-gadget surface
the default leaves open.

The allowlist is discovered from the modules the state actually references, so a
new evidence/orchestration type is covered automatically instead of silently
dropping back to the warned path.
"""

from __future__ import annotations

import enum
import inspect
from types import ModuleType

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from argus.domain import domain as _domain
from argus.domain import evidence as _evidence
from argus.domain import ioc as _ioc
from argus.domain import ipv4 as _ipv4
from argus.orchestration import models as _models
from argus.orchestration import state as _state

# Modules whose Pydantic models / enums may appear in a checkpointed
# InvestigationState. Extend this list if state gains a type from a new module.
_STATE_MODULES: tuple[ModuleType, ...] = (
    _ioc,
    _ipv4,
    _domain,
    _evidence,
    _models,
    _state,
)


def _allowed_types() -> list[type]:
    """Every serializable ARGUS type defined in the state modules."""
    allowed: list[type] = []
    for module in _STATE_MODULES:
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and obj.__module__ == module.__name__
                and issubclass(obj, (BaseModel, enum.Enum))
            ):
                allowed.append(obj)
    return allowed


def build_checkpointer() -> MemorySaver:
    """A MemorySaver that only deserializes ARGUS's registered state types."""
    serde = JsonPlusSerializer(allowed_msgpack_modules=_allowed_types())
    return MemorySaver(serde=serde)
