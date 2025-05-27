from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, Enum, String

from .base import Base

if TYPE_CHECKING:
    from .messages import Message
    from .users import User


class ConversationStatus(enum.Enum):
    """Defines the possible states of a conversation.

    States:
        ACTIVE:    Default state for ongoing conversations
        INACTIVE:  Set when no activity detected for >2 hours
        EXPIRED:   Set when conversation exceeds 24-hour limit
        CLOSING:   Set when bot indicates conversation should end
        CLOSED:    Set by message service
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    CLOSING = "closing"
    CLOSED = "closed"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        index=True,
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    # Status
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus), default=ConversationStatus.ACTIVE, nullable=False
    )

    # Vapi control URL for call transfer
    vapi_control_url: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    # Relationships
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    user: Mapped["User"] = relationship("User", back_populates="conversations")
    messages: Mapped[List["Message"]] = relationship(
        "Message", back_populates="conversation"
    )
