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
from .types import Channel

if TYPE_CHECKING:
    from .messages import Message
    from .users import User


class ConversationStatus(enum.Enum):
    """Defines the possible states of a conversation.

    States:
        ACTIVE:    Default state for ongoing conversations
        INACTIVE:  Set when no activity detected for >2 hours
        EXPIRED:   Deprecated - kept for backwards compatibility
        CLOSING:   Set when bot indicates conversation should end
        CLOSED:    Set by message service
    """

    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"  # Deprecated - kept for backwards compatibility
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
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=True,  # to stay compatible with historical conversations
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    # Status
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus), default=ConversationStatus.ACTIVE, nullable=False
    )

    # Test flag - marks if conversation started with a test message
    is_test: Mapped[bool] = mapped_column(
        default=False, nullable=False, server_default=text("false")
    )

    # Legacy VAPI control URL for call transfer (deprecated, LiveKit uses room_name)
    vapi_control_url: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    # Voice call identifier for call transfer and tracking
    call_id: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    # Channel that initiated this conversation (sms, voice, whatsapp, etc.)
    channel: Mapped[Optional[Channel]] = mapped_column(
        Enum(Channel, values_callable=lambda obj: [e.value for e in obj]), nullable=True
    )

    # Conversation purpose (ordering, reservation, waitlist, etc.)
    purpose: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    # Language of the conversation (english, french, spanish, chinese, etc.)
    language: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    # Conversation ended reason (customer_ended, assistant_forwarded, etc.)
    ended_reason: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    # Reason for transferring call to human (from call_transfer tool)
    transfer_purpose: Mapped[Optional[str]] = mapped_column(String(), nullable=True)

    # Order/transaction ID if customer successfully converted (ordered and paid)
    customer_converted: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Fingerprints for agent/prompt version tracking
    agent_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    prompt_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )

    # Relationships
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    user: Mapped["User"] = relationship("User", back_populates="conversations")
    messages: Mapped[List["Message"]] = relationship(
        "Message", back_populates="conversation"
    )
