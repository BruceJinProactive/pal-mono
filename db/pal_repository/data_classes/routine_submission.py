from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class RoutineSubmissionData:
    """Immutable snapshot of a routine submission.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    execution_id: uuid.UUID
    status: str
    created_at: datetime
    submitted_by: uuid.UUID | None = None
    submitted_at: datetime | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    updated_at: datetime | None = None
