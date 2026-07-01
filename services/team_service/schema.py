"""
Parameter schemas for team service operations.

These dataclasses define the parameters for team management operations,
following the repository pattern for clean service interfaces.
"""

from dataclasses import dataclass
from uuid import UUID

# Role precedence lists for determining primary role (highest to lowest priority).
# Legacy owner/manager/viewer remain readable during migration, but new
# customer-console writes should only create account_admin, store_owner, and
# store_member.
ACCOUNT_ROLE_PRECEDENCE: list[str] = [
    "account_admin",
    "owner",
    "manager",
    "viewer",
]
PROJECT_ROLE_PRECEDENCE: list[str] = [
    "store_owner",
    "store_member",
    "manager",
    "viewer",
]


@dataclass
class InvitationParams:
    """Parameters for creating a team member invitation.

    For account_admin access: project_ids must be None.
    For store_owner/store_member access: project_ids must be a non-empty list.
    """

    email: str
    account_role: str  # 'account_admin', 'store_owner', or 'store_member'
    project_ids: list[UUID] | None = None


@dataclass
class UpdateMemberRoleParams:
    """Parameters for updating a team member's role."""

    account_role: str  # currently only 'account_admin' until scoped updates land


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
