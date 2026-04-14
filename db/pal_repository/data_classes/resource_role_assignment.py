from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class ResourceRoleAssignmentData:
    """Immutable snapshot of a resource role assignment.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    resource_type: str
    resource_id: uuid.UUID
    role: str
    assigned_at: datetime
    created_at: datetime
    assigned_by: uuid.UUID | None = None
    reason: str | None = None
    updated_at: datetime | None = None
