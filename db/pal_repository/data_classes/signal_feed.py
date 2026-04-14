from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class SignalFeedData:
    """Immutable snapshot of a signal feed.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    source_id: uuid.UUID
    feed_type: str
    capture_mode: str
    status: str
    capture_count: int
    created_at: datetime
    status_message: str | None = None
    last_capture_at: datetime | None = None
    last_capture_url: str | None = None
    updated_at: datetime | None = None
