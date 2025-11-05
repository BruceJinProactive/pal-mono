from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String, Text

from .base import Base

if TYPE_CHECKING:
    pass


class Permission(Base):
    """Stores all available permissions in the system.

    Permissions follow the format: 'resource.action' (e.g., 'project.create', 'account.read')
    """

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "name ~ '^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$'",
            name="permission_name_format_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<Permission(name={self.name}, resource_type={self.resource_type}, action={self.action})>"
