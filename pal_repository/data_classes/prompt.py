from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PromptData:
    """Immutable snapshot of a prompt record.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.

    Enum fields are serialised to plain strings so that consumers do not
    depend on ``db.tables.types``.
    """

    id: uuid.UUID
    name: str
    resource_id: uuid.UUID
    resource_type: str
    deleted: bool
    created_at: datetime
    updated_at: datetime | None
    default_prompt_id: str | None = None
    channel: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PromptDetailsData:
    """Immutable snapshot of a prompt details (version) record.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    prompt_id: uuid.UUID
    version_number: int
    content: str
    created_by: str
    created_at: datetime
    updated_at: datetime | None
    change_summary: str | None = None
