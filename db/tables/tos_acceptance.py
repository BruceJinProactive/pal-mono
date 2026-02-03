from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base


class TosAcceptance(Base):
    """Terms of Service acceptance audit history.

    This table stores the full history of WHO accepted WHICH VERSION of the Terms of Service and WHEN for each account.
    Each acceptance of a new ToS version creates a new record, allowing full audit trail.
    Unique constraint on (account_id, tos_version) ensures each account can accept each version only once.
    account_id provides immutable reference; display_name is a snapshot for convenience.
    """

    __tablename__ = "tos_acceptances"
    __table_args__ = (
        # Ensure each account can accept each ToS version only once
        # This allows multiple records per account (one per version) for full audit history
        # Uses account_id (immutable)
        UniqueConstraint(
            "account_id", "tos_version", name="uq_tos_acceptances_account_version"
        ),
        # Index for audit queries filtering by user (e.g., "show all ToS acceptances by user")
        Index("ix_tos_acceptances_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # immutable account reference
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )

    # display name at time of acceptance
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # version of ToS accepted
    tos_version: Mapped[str] = mapped_column(String(50), nullable=False)

    # accepts from which account
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)

    # when was tos accepted
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=func.now(),
    )
