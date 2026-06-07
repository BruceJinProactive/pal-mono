from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from db.tables.catering_request_activities import (
    CateringRequestActivityActorType,
    CateringRequestActivitySource,
    CateringRequestActivityType,
)


@dataclass(frozen=True)
class CateringRequestActivityData:
    """Immutable snapshot of a catering request activity."""

    id: uuid.UUID
    catering_request_id: uuid.UUID
    project_id: uuid.UUID
    activity_type: CateringRequestActivityType
    actor_type: CateringRequestActivityActorType
    actor_display_name: str
    description: str
    source: CateringRequestActivitySource
    occurred_at: datetime
    created_at: datetime
    actor_id: uuid.UUID | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = 1
