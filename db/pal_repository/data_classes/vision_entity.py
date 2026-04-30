from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass(frozen=True)
class VisionEntityData:
    id: uuid.UUID
    project_id: uuid.UUID
    entity_type_id: uuid.UUID
    name: str
    is_active: bool
    entity_metadata: Dict[str, object]
    created_at: datetime
    current_state_id: uuid.UUID | None = None
    current_state_since: datetime | None = None
    updated_at: datetime | None = None
