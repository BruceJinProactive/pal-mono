from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


def _freeze(value: Any) -> Any:
    """Recursively freeze mutable containers into immutable equivalents."""
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set):
        return frozenset(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class EvalResultData:
    """Immutable snapshot of an eval result.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    eval_run_id: uuid.UUID
    scenario_id: str
    metric_name: str
    score: float
    passed: bool
    evaluated_at: datetime
    conversation_id: uuid.UUID | None = None
    agent_fingerprint: str | None = None
    reason: str | None = None
    raw_output: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.raw_output is not None:
            object.__setattr__(self, "raw_output", _freeze(dict(self.raw_output)))
