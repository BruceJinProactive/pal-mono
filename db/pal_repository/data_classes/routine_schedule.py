from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class RoutineScheduleData:
    """Immutable snapshot of a routine schedule.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    routine_id: uuid.UUID
    frequency: str
    start_time: time
    end_time: time
    timezone: str
    is_active: bool
    created_at: datetime
    days_of_week: tuple[int, ...] | None = None
    day_of_month: int | None = None
    interval_hours: int | None = None
    effective_from: date | None = None
    effective_until: date | None = None
    updated_at: datetime | None = None
