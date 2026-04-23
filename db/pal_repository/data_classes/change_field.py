from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ChangeFieldData:
    """Immutable snapshot of a change field entry.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    change_log_id: uuid.UUID
    field: str
    old_value: str | None = None
    new_value: str | None = None
