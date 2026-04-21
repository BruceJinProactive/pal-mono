from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FAQData:
    """Immutable snapshot of a FAQ.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    question: str
    answer: str
    created_at: datetime
    project_id: uuid.UUID | None = None
    updated_at: datetime | None = None
