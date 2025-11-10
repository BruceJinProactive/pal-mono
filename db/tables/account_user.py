from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime

from .base import Base
from .types import AccountUserStatus

if TYPE_CHECKING:
    pass


class AccountUser(Base):
    """User membership in an account.

    IMPORTANT: This table tracks membership only (membership ≠ permissions).
    Roles are assigned via the ResourceRoleAssignment table.
    This separation allows for flexible role assignment on different resources.
    """

    __tablename__ = "account_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    status: Mapped[AccountUserStatus] = mapped_column(
        Enum(AccountUserStatus),
        nullable=False,
        server_default=AccountUserStatus.active.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("account_id", "user_id", name="uq_account_user"),
    )

    def __repr__(self) -> str:
        return f"<AccountUser(user_id={self.user_id}, name={self.name}, email={self.email}, account_id={self.account_id}, status={self.status.value})>"
