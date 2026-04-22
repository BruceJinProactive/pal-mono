from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LeadData:
    """Immutable snapshot of a lead.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    status: str
    contract_signed: bool
    deleted: bool
    created_at: datetime
    business_name: str | None = None
    business_address: str | None = None
    logo_uri: str | None = None
    segment: str | None = None
    tier: str | None = None
    pos: str | None = None
    channels: tuple[str, ...] = ()
    account_id: uuid.UUID | None = None
    owner: str | None = None
    hubspot_record_id: str | None = None
    notes: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "channels", tuple(self.channels) if self.channels else ()
        )
