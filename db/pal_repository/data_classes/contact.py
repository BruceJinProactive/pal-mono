from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class ContactData:
    """Immutable snapshot of a contact.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    name: str
    phone_number: str
    role: str
    created_at: datetime
    email: str | None = None
    updated_at: datetime | None = None
