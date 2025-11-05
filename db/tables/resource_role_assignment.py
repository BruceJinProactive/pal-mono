from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String, Text

from .base import Base

if TYPE_CHECKING:
    pass


class ResourceRoleAssignment(Base):
    """Unified table for ALL role assignments on ANY resource.

    This table handles role assignments for:
    - Account-level: resource_type='account', resource_id=account_id
    - Project-level: resource_type='project', resource_id=project_id
    - Agent-level: resource_type='agent', resource_id=agent_id
    - Any future resource types

    Design principle: No inheritance or overrides - simple lookup:
    "What role does this user have on THIS specific resource?"

    Roles are arbitrary strings allowing flexible role definitions.
    Examples: 'owner', 'manager', 'viewer', 'billing_admin', 'content_editor', etc.
    """

    __tablename__ = "resource_role_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=func.now()
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "resource_type",
            "resource_id",
            name="uq_user_resource_role",
        ),
    )

    def __repr__(self) -> str:
        return f"<ResourceRoleAssignment(user_id={self.user_id}, resource_type={self.resource_type}:{self.resource_id}, role={self.role})>"
