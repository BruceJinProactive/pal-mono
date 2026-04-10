from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class TosAcceptanceData:
    """Immutable snapshot of a TOS acceptance record.

    ORM objects never leave the repository layer — only this record
    is returned to callers.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    display_name: str
    tos_version: str
    user_id: uuid.UUID
    user_email: str
    accepted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
