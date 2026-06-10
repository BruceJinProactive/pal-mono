from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any


@dataclass(frozen=True)
class CateringRequestData:
    """Immutable snapshot of a catering request.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    project_id: uuid.UUID
    event_date: date
    contact_name: str
    contact_phone_number: str
    status: str
    idempotency_key: str
    created_at: datetime
    updated_at: datetime
    event_time: time | None = None
    event_address: str | None = None
    event_detail: str | None = None
    all_items: dict[str, dict[str, Any]] | None = None
    event_fulfillment: str | None = None
    party_size: int | None = None
    contact_id: uuid.UUID | None = None
