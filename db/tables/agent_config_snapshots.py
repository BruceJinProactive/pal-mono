from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict

from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String, Text

from .base import Base


class AgentConfigSnapshot(Base):
    __tablename__ = "agent_config_snapshots"

    fingerprint: Mapped[str] = mapped_column(
        String(64), primary_key=True, nullable=False
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    system_prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    system_prompt_text: Mapped[str] = mapped_column(Text, nullable=False)

    config_snapshot: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
