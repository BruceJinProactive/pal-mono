from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class SignalSourceData:
    """Immutable snapshot of a signal source.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    signal_type: str
    name: str
    status: str
    config: Dict
    created_at: datetime
    project_id: uuid.UUID | None = None
    description: str | None = None
    status_message: str | None = None
    updated_at: datetime | None = None
