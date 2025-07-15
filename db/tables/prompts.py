from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Enum, String, Text

from .base import Base
from .types import AgentType, Channel, Language, PlanTier


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[Optional[list[Channel]]] = mapped_column(
        ARRAY(Enum(Channel)), nullable=True
    )
    agent_type: Mapped[Optional[list[AgentType]]] = mapped_column(
        ARRAY(Enum(AgentType)), nullable=True
    )
    plan_tier: Mapped[Optional[list[PlanTier]]] = mapped_column(
        ARRAY(Enum(PlanTier)), nullable=True
    )
    language: Mapped[Optional[list[Language]]] = mapped_column(
        ARRAY(Enum(Language)), nullable=True
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    resource_type: Mapped[str] = mapped_column(String, nullable=False)
    deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # Metadata columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    # Relationships
    prompt_details: Mapped[List["PromptDetails"]] = relationship(
        "PromptDetails", back_populates="prompt"
    )


class PromptDetails(Base):
    __tablename__ = "prompt_details"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )
    # Relationships
    prompt: Mapped["Prompt"] = relationship("Prompt", back_populates="prompt_details")

    __table_args__ = (
        UniqueConstraint("prompt_id", "version_number", name="uq_prompt_version"),
    )
