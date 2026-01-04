from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.types import Boolean, DateTime, Integer, String

from .base import Base


class AgentCapability(Base):
    """
    Agent-specific capability enablement and configuration.
    Links agents to capabilities with priority and enabled status.
    """

    __tablename__ = "agent_capabilities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )

    # Reference to agent (indexed, no FK)
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Capability identifier (e.g., 'ordering', 'reservation')
    capability_identifier: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    # Priority for capabilities (lower number = higher priority)
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=50,
    )

    # Whether this capability is enabled for the agent
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
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

    # Unique constraint on agent_id + capability_identifier
    __table_args__ = (
        UniqueConstraint(
            "agent_id", "capability_identifier", name="uq_agent_capability"
        ),
        {"schema": None, "extend_existing": True},
    )

    def __repr__(self) -> str:
        return f"<AgentCapability(agent_id={self.agent_id}, capability={self.capability_identifier}, enabled={self.enabled})>"
