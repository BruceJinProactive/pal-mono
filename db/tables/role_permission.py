from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base

if TYPE_CHECKING:
    pass


class RolePermission(Base):
    """Junction table mapping roles to permissions.

    Roles are arbitrary strings allowing flexible role definitions.
    Examples: 'owner', 'manager', 'viewer', 'billing_admin', 'content_editor', etc.
    """

    __tablename__ = "role_permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("role", "permission_id", name="uq_role_permission"),
    )

    def __repr__(self) -> str:
        return f"<RolePermission(role={self.role}, permission_id={self.permission_id})>"
