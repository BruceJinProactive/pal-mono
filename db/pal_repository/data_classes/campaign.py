from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CampaignData:
    """Immutable snapshot of a campaign.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    name: str
    message: str
    channel: str
    internal_recipient: bool
    created_at: datetime
    updated_at: datetime | None = None


@dataclass(frozen=True)
class CampaignMessageData:
    """Immutable snapshot of a campaign message.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    campaign_id: uuid.UUID
    recipient: str
    status: str
    created_at: datetime
    error_detail: str | None = None
    updated_at: datetime | None = None
