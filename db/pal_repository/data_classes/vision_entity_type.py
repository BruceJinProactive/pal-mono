from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class VisionEntityTypeData:
    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    display_name: str
    is_active: bool
    created_at: datetime
    description: str | None = None
    icon: str | None = None
    updated_at: datetime | None = None
