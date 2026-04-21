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
class AgentData:
    """Immutable snapshot of an agent.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    agent_type: str
    speech_rate: str
    language: str
    has_voice_clone: bool
    background_noise: bool
    memory_enabled: bool
    created_at: datetime
    description: str | None = None
    communication_style: str | None = None
    interaction_guidelines: str | None = None
    voice_id: str | None = None
    cloned_voice_id: str | None = None
    greeting_message: str | None = None
    filler_words: Mapping[str, Any] = field(default_factory=dict)
    raw_config: Mapping[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "filler_words", _freeze(dict(self.filler_words)))
        object.__setattr__(self, "raw_config", _freeze(dict(self.raw_config)))
