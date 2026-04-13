from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class RolePermissionData:
    """Immutable snapshot of a role-permission mapping.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    role: str
    permission_id: uuid.UUID
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
