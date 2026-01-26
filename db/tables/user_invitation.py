from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.expression import text
from sqlalchemy.types import DateTime, String

from .base import Base
from .types import InvitationStatus

if TYPE_CHECKING:
    pass


class UserInvitation(Base):
    """Team member invitations.

    On acceptance, creates:
    1. AccountUser record (membership)
    2. ResourceRoleAssignment record (role on account or project resource)

    Token must be cryptographically secure (use secrets.token_urlsafe(48))

    Roles are arbitrary strings allowing flexible role definitions.
    Examples: 'owner', 'manager', 'viewer', 'staff', etc.

    Project-level assignments:
    - If project_ids is NULL: Creates account-level role (access to all projects)
    - If project_ids is a list: Creates project-level role for each project
    """

    __tablename__ = "user_invitations"

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
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    account_role: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Role to assign on acceptance"
    )
    project_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        comment="Project IDs to assign on acceptance, NULL = account-level access",
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    invitation_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus),
        nullable=False,
        server_default=InvitationStatus.pending.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Constraints
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="check_expires_after_created"),
    )

    def __repr__(self) -> str:
        project_info = f", project_ids={self.project_ids}" if self.project_ids else ""
        return f"<UserInvitation(email={self.email}, account_id={self.account_id}, account_role={self.account_role}{project_info}, status={self.status.value})>"
