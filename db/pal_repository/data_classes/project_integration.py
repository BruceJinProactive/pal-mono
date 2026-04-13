from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class ProjectIntegrationData:
    """Immutable snapshot of a project-integration link.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    project_id: uuid.UUID
    integration_id: uuid.UUID
    store_identifier: str
    created_at: datetime
    tool_name: str | None = None
    config: dict[str, object] = field(default_factory=dict)
