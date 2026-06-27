from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class PhoneCallData:
    """Immutable snapshot of a phone call record.

    ORM objects never leave the repository layer — only this record
    is returned to callers.

    Enum fields are serialised to plain strings so that consumers do not
    depend on ``db.tables.types``.
    """

    id: uuid.UUID
    call_id: str
    conversation_id: uuid.UUID
    duration: float | None = None
    turn_latency_avg: float | None = None
    model_latency_avg: float | None = None
    voice_latency_avg: float | None = None
    transcriber_latency_avg: float | None = None
    endpointing_latency_avg: float | None = None
    ended_reason: str | None = None
    call_purpose: tuple[str, ...] = field(default_factory=tuple)
    user_satisfaction: str | None = None
    language: str | None = None
    transfer_reason_category: str | None = None
    transfer_agent_was_at_fault: bool | None = None
    call_quality_label: str | None = None
    call_quality_reason_codes: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
