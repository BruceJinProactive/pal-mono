from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from db.pal_repository.data_classes.change_field import ChangeFieldData


@dataclass(frozen=True)
class ChangeLogData:
    """Immutable snapshot of a change log entry.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    resource_type: str
    resource_id: str
    author: str
    action: str
    created_at: datetime
    fields: tuple[ChangeFieldData, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", tuple(self.fields))
