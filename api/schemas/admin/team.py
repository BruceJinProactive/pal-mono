"""
Team management and invitation schemas for Phase 3 RBAC implementation.

This module provides Pydantic schemas for:
- Team member invitation and management
- Invitation acceptance flow
- Multi-account support
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


# Enums
class UserRole(str, Enum):
    """User roles for account-level permissions."""

    OWNER = "owner"
    MANAGER = "manager"
    VIEWER = "viewer"


class InvitationStatus(str, Enum):
    """Status of team member invitations."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# Team Management Schemas
class InviteTeamMemberRequest(BaseModel):
    """Request to invite a new team member."""

    email: EmailStr
    account_role: UserRole


class InvitationResponse(BaseModel):
    """Response after creating an invitation."""

    invitation_id: UUID
    email: str
    account_role: UserRole
    invitation_token: str
    expires_at: datetime
    status: InvitationStatus


class TeamMemberResponse(BaseModel):
    """Individual team member details."""

    user_id: UUID
    email: str
    name: Optional[str] = None
    account_role: Optional[UserRole] = None
    status: str  # active, deactivated
    added_at: datetime
    last_active: Optional[datetime] = None
    resource_roles: List[dict] = []  # Empty for V1, future project/agent roles


class TeamInvitationResponse(BaseModel):
    """Pending invitation details for team list."""

    invitation_id: UUID
    email: str
    account_role: UserRole
    status: str  # pending


class TeamMembersListResponse(BaseModel):
    """List of team members and pending invitations."""

    members: List[TeamMemberResponse]
    invitations: List[TeamInvitationResponse]


class UpdateTeamMemberRequest(BaseModel):
    """Request to update a team member's role."""

    account_role: UserRole


class UpdateTeamMemberResponse(BaseModel):
    """Response after updating team member role."""

    user_id: UUID
    account_role: UserRole
    updated_at: datetime


# Invitation Flow Schemas
class InvitationDetailsResponse(BaseModel):
    """Public invitation details (no auth required)."""

    account_name: str
    account_display_name: str | None = None
    invited_by: str  # name or email of inviter
    role: UserRole
    expires_at: datetime
    status: InvitationStatus


class AcceptInvitationRequest(BaseModel):
    """Request to accept an invitation."""

    invitation_token: str


class AcceptInvitationResponse(BaseModel):
    """Response after accepting invitation."""

    account_id: UUID
    account_name: str
    account_role: UserRole
    message: str


class ResendInvitationResponse(BaseModel):
    """Response after resending invitation."""

    message: str
    invitation_id: UUID


class DecodeInvitationTokenRequest(BaseModel):
    """Request to decode an invitation JWT token."""

    token: str


class DecodeInvitationTokenResponse(BaseModel):
    """Response with decoded invitation credentials."""

    invitation_token: str
    email: str
    temporary_password: Optional[str] = None


class PendingInvitationResponse(BaseModel):
    """Pending invitation for a user."""

    invitation_id: UUID
    invitation_token: str
    account_name: str
    account_display_name: Optional[str] = None
    invited_by: str  # name or email of inviter
    role: UserRole
    expires_at: datetime
    status: InvitationStatus


class UserPendingInvitationsResponse(BaseModel):
    """List of pending invitations for a user."""

    invitations: List[PendingInvitationResponse]


class AcceptMultipleInvitationsRequest(BaseModel):
    """Request to accept multiple invitations at once."""

    invitation_tokens: List[str]


class AcceptedInvitationResult(BaseModel):
    """Result of accepting a single invitation."""

    invitation_token: str
    account_id: Optional[UUID] = None
    account_name: Optional[str] = None
    account_role: Optional[UserRole] = None
    success: bool
    error: Optional[str] = None


class AcceptMultipleInvitationsResponse(BaseModel):
    """Response after accepting multiple invitations."""

    results: List[AcceptedInvitationResult]
    total: int
    successful: int
    failed: int


# Multi-Account Support Schemas
class UserAccountResponse(BaseModel):
    """Account information for account switcher."""

    account_id: UUID
    account_name: str
    role: Optional[UserRole] = None
    last_accessed: Optional[datetime] = None


class UserAccountWithUserIdResponse(BaseModel):
    """Account information with user_id (for admin lookup by email)."""

    user_id: UUID
    account_id: UUID
    account_name: str
    role: Optional[UserRole] = None
    last_accessed: Optional[datetime] = None


class UserAccountsListResponse(BaseModel):
    """List of accounts user has access to."""

    accounts: List[UserAccountResponse]


class UserAccountsWithUserIdListResponse(BaseModel):
    """List of accounts with user_id (for admin lookup by email)."""

    accounts: List[UserAccountWithUserIdResponse]


class SwitchAccountRequest(BaseModel):
    """Request to switch active account."""

    account_id: UUID


class SwitchAccountResponse(BaseModel):
    """Response after switching account."""

    account_id: UUID
    account_name: str
    role: Optional[UserRole] = None
