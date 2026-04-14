from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class PermissionData:
    """Immutable snapshot of a permission.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    name: str
    resource_type: str
    action: str
    display_name: str
    created_at: datetime
    description: str | None = None
