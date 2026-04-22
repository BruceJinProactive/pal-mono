from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class MonitoringConfigData:
    """Immutable snapshot of a monitoring config.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    project_id: uuid.UUID
    signal_source_id: uuid.UUID
    name: str
    enabled: bool
    created_at: datetime
    description: str | None = None
    rules: Mapping[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", MappingProxyType(deepcopy(dict(self.rules))))
        object.__setattr__(self, "tags", tuple(self.tags) if self.tags else ())
