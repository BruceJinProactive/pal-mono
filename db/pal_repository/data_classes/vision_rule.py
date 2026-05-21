from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class VisionRuleData:
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    type: str
    severity: str
    is_active: bool
    rule_metadata: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
