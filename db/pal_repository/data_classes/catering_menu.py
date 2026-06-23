from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class CateringMenuData:
    """Immutable snapshot of a catering menu item."""

    id: uuid.UUID
    project_id: uuid.UUID
    account_id: uuid.UUID | None
    item_name: str
    item_price: Decimal
    created_at: datetime
    updated_at: datetime
