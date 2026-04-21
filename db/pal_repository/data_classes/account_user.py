from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AccountUserData:
    """Immutable snapshot of an account-user membership.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    user_id: uuid.UUID
    status: str
    added_at: datetime
    created_at: datetime
    updated_at: datetime
    name: str | None = None
    email: str | None = None
    added_by: uuid.UUID | None = None
