from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class VisionRuleEventData:
    id: uuid.UUID
    rule_id: uuid.UUID
    entity_id: uuid.UUID
    state_change_event_id: uuid.UUID
    severity: str
    triggered_at: datetime
    event_metadata: dict[str, Any] = field(default_factory=dict)
