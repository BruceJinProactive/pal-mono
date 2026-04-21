from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CapabilityActionData:
    """Immutable snapshot of a capability action.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    agent_capability_id: uuid.UUID
    action: str
    prompt: str
    channel: str
    priority: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
