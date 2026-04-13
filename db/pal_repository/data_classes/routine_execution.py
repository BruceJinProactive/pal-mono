from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from db.tables.types import ExecutionStatus


class _Unset(Enum):
    """Sentinel that distinguishes 'not provided' from an explicit ``None``."""

    UNSET = "UNSET"


UNSET: _Unset = _Unset.UNSET


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class RoutineExecutionData:
    """Immutable snapshot of a routine execution.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    routine_id: uuid.UUID
    schedule_id: uuid.UUID
    scheduled_start: datetime
    scheduled_end: datetime
    status: ExecutionStatus
    created_at: datetime
    assigned_user_id: uuid.UUID | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class RoutineExecutionUpdateData:
    """Partial-update payload for a routine execution.

    All fields are optional — only non-None values overwrite the existing record.
    For ``assigned_user_id``, use ``None`` to explicitly unassign; leave as
    ``UNSET`` (default) to skip the update.
    """

    status: ExecutionStatus | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    assigned_user_id: uuid.UUID | None | _Unset = field(default=UNSET)
