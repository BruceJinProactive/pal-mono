from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ToolCallRecordData:
    """Immutable snapshot of a tool call record.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    conversation_id: uuid.UUID
    tool_name: str
    is_error: bool
    created_at: datetime
    error_type: str | None = None
    duration_ms: int | None = None
    result: str | None = None
