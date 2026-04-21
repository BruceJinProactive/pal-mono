from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FeedbackData:
    """Immutable snapshot of a feedback entry.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    message_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    author_identifier: str | None = None
    author_name: str | None = None
    reaction: str | None = None
    tags: tuple[str, ...] = ()
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", tuple(self.tags) if self.tags else ())
