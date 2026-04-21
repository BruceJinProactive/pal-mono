from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AffiliateData:
    """Immutable snapshot of an affiliate.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    rewardful_id: str
    created_at: datetime
    updated_at: datetime | None = None
