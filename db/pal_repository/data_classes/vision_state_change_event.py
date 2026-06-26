from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class VisionStateChangeEventData:
    id: uuid.UUID
    entity_id: uuid.UUID
    new_state_id: uuid.UUID
    observed_at: datetime
    event_metadata: dict[str, Any] = field(default_factory=dict)
    camera_config_id: uuid.UUID | None = None
    previous_state_id: uuid.UUID | None = None
    frame_s3_key: str | None = None


@dataclass(frozen=True)
class VisionStateChangeEventPage:
    items: list[VisionStateChangeEventData]
    total: int
