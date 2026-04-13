from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class ReservationData:
    """Immutable snapshot of a reservation record.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.

    Enum fields are serialised to plain strings so that consumers do not
    depend on ``db.tables.types``.
    """

    id: uuid.UUID
    conversation_id: uuid.UUID
    entry_type: str
    created_at: datetime
    updated_at: datetime | None
    reservation_id: str | None = None
    store_id: str | None = None
    tracking_link: str | None = None
    status: str | None = None
    vendor: str | None = None
    table_size: int | None = None
    special_requests: str | None = None
    arrive_by_time: datetime | None = None
    expected_seating_time: datetime | None = None
    reservation_time: datetime | None = None
