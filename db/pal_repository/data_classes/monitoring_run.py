from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class MonitoringRunData:
    """Immutable snapshot of a monitoring run.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    monitoring_config_id: uuid.UUID
    started_at: datetime
    trigger_metadata: Mapping[str, Any] = field(default_factory=dict)
    evaluation_result: Mapping[str, Any] = field(default_factory=dict)
    completed_at: datetime | None = None
    result: str | None = None
    details: str | None = None
    confidence: int | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "trigger_metadata",
            MappingProxyType(deepcopy(dict(self.trigger_metadata))),
        )
        object.__setattr__(
            self,
            "evaluation_result",
            MappingProxyType(deepcopy(dict(self.evaluation_result))),
        )
