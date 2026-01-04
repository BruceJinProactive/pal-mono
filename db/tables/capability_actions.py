from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime, Integer, String, Text

from .base import Base


class CapabilityAction(Base):
    """
    Action overrides for agent capabilities.
    Stores custom prompts for specific actions within a capability.
    """

    __tablename__ = "capability_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )

    # Reference to agent_capability (indexed, no FK)
    agent_capability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Action name (e.g., 'create_order', 'cancel_order')
    action: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    # Custom prompt override
    prompt: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # Channel-specific override (SMS, VOICE, EMAIL, ALL)
    # Default 'ALL' means applies to all channels
    channel: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="ALL",
        server_default="ALL",
        index=True,
    )

    # Priority for ordering actions (lower number = higher priority)
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=50,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Unique constraint on agent_capability_id + action + channel
    __table_args__ = (
        UniqueConstraint(
            "agent_capability_id",
            "action",
            "channel",
            name="uq_capability_action_channel",
        ),
        {"schema": None, "extend_existing": True},
    )

    def __repr__(self) -> str:
        return f"<CapabilityAction(agent_capability_id={self.agent_capability_id}, action={self.action}, channel={self.channel})>"
