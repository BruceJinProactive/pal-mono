from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class UserData:
    """Immutable snapshot of a user.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    account_id: uuid.UUID
    created_at: datetime
    raw_config: dict[str, Any] = field(default_factory=dict)
    channel_identifiers: tuple[str, ...] | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.channel_identifiers is not None and not isinstance(
            self.channel_identifiers, tuple
        ):
            object.__setattr__(
                self, "channel_identifiers", tuple(self.channel_identifiers)
            )
