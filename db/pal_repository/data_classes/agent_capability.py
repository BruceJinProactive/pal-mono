from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AgentCapabilityData:
    """Immutable snapshot of an agent capability.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    agent_id: uuid.UUID
    capability_identifier: str
    priority: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
