from __future__ import annotations

import uuid
from dataclasses import dataclass, field
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
class AgentConfigSnapshotData:
    """Immutable snapshot of an agent config snapshot.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    fingerprint: str
    agent_id: uuid.UUID
    project_id: uuid.UUID
    system_prompt_hash: str
    system_prompt_text: str
    first_seen_at: datetime
    last_seen_at: datetime
    config_snapshot: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_snapshot", _freeze(dict(self.config_snapshot)))
