from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from db.tables.types import RoutineCategory


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class RoutineData:
    """Immutable snapshot of a routine.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    category: RoutineCategory
    created_at: datetime
    description: str | None = None
    is_active: bool | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class RoutineUpdateData:
    """Partial-update payload for a routine.

    All fields are optional — only non-None values overwrite the existing record.
    """

    name: str | None = None
    description: str | None = None
    category: RoutineCategory | None = None
    is_active: bool | None = None
