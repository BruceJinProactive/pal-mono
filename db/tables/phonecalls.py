from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import ARRAY, DateTime, Enum, Float, String

from .base import Base
from .types import CallEndedReason, CallLanguage, CallPurpose, UserSatisfaction


class PhoneCall(Base):
    __tablename__ = "phone_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    call_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    turn_latency_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_latency_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    voice_latency_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    transcriber_latency_avg: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    endpointing_latency_avg: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    ended_reason: Mapped[Optional[CallEndedReason]] = mapped_column(
        Enum(CallEndedReason), nullable=True
    )
    call_purpose: Mapped[Optional[list[CallPurpose]]] = mapped_column(
        ARRAY(Enum(CallPurpose)), nullable=True
    )
    user_satisfaction: Mapped[Optional[UserSatisfaction]] = mapped_column(
        Enum(UserSatisfaction), nullable=True
    )
    language: Mapped[Optional[CallLanguage]] = mapped_column(
        Enum(CallLanguage), nullable=True
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
