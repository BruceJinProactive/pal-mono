from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VisionEntityStateDefinitionData:
    id: uuid.UUID
    entity_type_id: uuid.UUID
    name: str
    display_name: str
    sort_order: int
    is_default: bool
    created_at: datetime
    color: str | None = None
