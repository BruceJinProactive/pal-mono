from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass(frozen=True)
class VisionCameraEntityData:
    id: uuid.UUID
    camera_config_id: uuid.UUID
    entity_id: uuid.UUID
    created_at: datetime
    roi_hint: Dict[str, object] | None = None
