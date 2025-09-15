from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Enum, String

from .base import Base
from .types import AgentType, Language, SpeechRate

if TYPE_CHECKING:
    from .accounts import Account
    from .projects import Project


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String, nullable=False, server_default="assistant"
    )
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    communication_style: Mapped[str | None] = mapped_column(String, nullable=True)
    interaction_guidelines: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_type: Mapped[AgentType] = mapped_column(
        Enum(AgentType), nullable=False, server_default=AgentType.general
    )
    voice_id: Mapped[str | None] = mapped_column(String, nullable=True)
    greeting_message: Mapped[str | None] = mapped_column(String, nullable=True)
    speech_rate: Mapped[SpeechRate] = mapped_column(
        Enum(SpeechRate), nullable=False, server_default=SpeechRate.normal
    )
    background_noise: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    language: Mapped[Language] = mapped_column(
        Enum(Language, name="agent_language"),
        nullable=False,
        server_default=Language.english,
    )
    filler_words: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    # deprecated, use the explicit fields instead
    raw_config: Mapped[Dict] = mapped_column(
        MutableDict.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    # Metadata columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    # Relationships
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True
    )
    account: Mapped["Account"] = relationship("Account", back_populates="agents")
    projects: Mapped[List["Project"]] = relationship("Project", back_populates="agent")
