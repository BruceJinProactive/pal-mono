"""
Parameter schemas for team service operations.

These dataclasses define the parameters for team management operations,
following the repository pattern for clean service interfaces.
"""

from dataclasses import dataclass
from uuid import UUID

# Role precedence lists for determining primary role (highest to lowest priority)
# Account-level roles: assigned to the account resource, grants access to all projects
ACCOUNT_ROLE_PRECEDENCE: list[str] = ["owner", "manager", "staff", "viewer"]
# Project-level roles: assigned to specific projects
PROJECT_ROLE_PRECEDENCE: list[str] = ["manager", "staff", "viewer"]


@dataclass
class InvitationParams:
    """Parameters for creating a team member invitation.

    For account-level access: project_ids is None (access to all projects)
    For project-level access: project_ids is a list of project UUIDs
    """

    email: str
    account_role: str  # 'owner', 'manager', 'viewer', or 'staff'
    project_ids: list[UUID] | None = None


@dataclass
class UpdateMemberRoleParams:
    """Parameters for updating a team member's role."""

    account_role: str  # 'owner', 'manager', 'staff', or 'viewer'


@dataclass
class AcceptInvitationParams:
    """Parameters for accepting an invitation."""

    invitation_token: str


@dataclass
class SwitchAccountParams:
    """Parameters for switching active account context."""

    account_id: UUID


@dataclass
class TeamMemberFilters:
    """Filters for listing team members."""

    role: str | None = None
    status: str | None = None
    search: str | None = None
