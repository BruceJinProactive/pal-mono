"""
Parameter schemas for team service operations.

These dataclasses define the parameters for team management operations,
following the repository pattern for clean service interfaces.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass
class InvitationParams:
    """Parameters for creating a team member invitation."""

    email: str
    account_role: str  # 'owner', 'manager', or 'viewer'


@dataclass
class UpdateMemberRoleParams:
    """Parameters for updating a team member's role."""

    account_role: str  # 'owner', 'manager', or 'viewer'


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
