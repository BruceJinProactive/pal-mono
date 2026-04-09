from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PromptDetailsData:
    """Immutable snapshot of a prompt details (version) record.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    prompt_id: uuid.UUID
    version_number: int
    content: str
    created_by: str
    created_at: datetime
    updated_at: datetime | None
    change_summary: str | None = None
