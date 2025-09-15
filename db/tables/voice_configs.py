from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Enum, String

from .base import Base
from .types import SpeechRate


class VoiceConfig(Base):
    __tablename__ = "voice_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String, nullable=False)
    voice_id: Mapped[str] = mapped_column(String, nullable=False)
    replacements: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )
    first_message: Mapped[str] = mapped_column(String, nullable=False)
    transfer_message: Mapped[str] = mapped_column(String, nullable=False)
    speech_rate: Mapped[SpeechRate] = mapped_column(
        Enum(SpeechRate, name="speechrate", native_enum=True, create_type=False),
        nullable=False,
        server_default=text("'normal'::speechrate"),
        default=SpeechRate.normal,
    )
    background_sound: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'office'"), default="office"
    )
    raw_config: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
    )

    # Metadata columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
