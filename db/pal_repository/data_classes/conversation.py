from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ConversationData:
    """Immutable snapshot of a conversation.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    is_test: bool
    created_at: datetime
    project_id: uuid.UUID | None = None
    channel: str | None = None
    purpose: str | None = None
    language: str | None = None
    ended_reason: str | None = None
    transfer_purpose: str | None = None
    customer_converted: uuid.UUID | None = None
    agent_fingerprint: str | None = None
    prompt_fingerprint: str | None = None
    vapi_control_url: str | None = None
    call_id: str | None = None
    updated_at: datetime | None = None
