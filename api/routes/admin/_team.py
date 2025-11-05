"""
Team management implementation for Phase 3 RBAC.

This module provides mock implementations for:
- Team member invitation and management
- Invitation acceptance flow
- Multi-account support

NOTE: These are minimal mocks to unblock frontend development.
All functions return proper schema structures with mock data.
"""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status

from api.routes.admin._auth import authorize_user_account
from api.routes.admin._utils import UserContext
from api.schemas.admin.team import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    InvitationDetailsResponse,
    InvitationResponse,
    InvitationStatus,
    InviteTeamMemberRequest,
    ResendInvitationResponse,
    SwitchAccountRequest,
    SwitchAccountResponse,
    TeamMembersListResponse,
    UpdateTeamMemberRequest,
    UpdateTeamMemberResponse,
    UserAccountResponse,
    UserAccountsListResponse,
    UserRole,
)

# ============================================================================
# TEAM MANAGEMENT ENDPOINTS
# ============================================================================


async def invite_team_member(
    account_name: str,
    request: InviteTeamMemberRequest,
    context: UserContext,
) -> InvitationResponse:
    """
    Invite a new team member with specified role.

    Mock: Returns a successful invitation with generated token.
    """
    # Authorize - owner only
    authorize_user_account(context, account_name)

    # Generate mock invitation
    invitation_id = uuid4()
    invitation_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    return InvitationResponse(
        invitation_id=invitation_id,
        email=request.email,
        account_role=request.account_role,
        invitation_token=invitation_token,
        expires_at=expires_at,
        status=InvitationStatus.PENDING,
    )


async def list_team_members(
    account_name: str,
    context: UserContext,
    role: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> TeamMembersListResponse:
    """
    List all team members for an account.

    Mock: Returns empty list with total=0.
    """
    # Authorize - any authenticated user with account access
    authorize_user_account(context, account_name)

    # Return empty list for minimal mock
    return TeamMembersListResponse(
        members=[],
        total=0,
    )


async def update_team_member_role(
    account_name: str,
    user_email: str,
    request: UpdateTeamMemberRequest,
    context: UserContext,
) -> UpdateTeamMemberResponse:
    """
    Update a team member's role.

    Mock: Returns success response with updated role.
    """
    # Authorize - owner only
    authorize_user_account(context, account_name)

    # Basic validation: prevent self-demotion if last owner
    if context.email == user_email and request.account_role != UserRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role if you are the last owner",
            headers={"Content-Type": "application/json"},
        )

    return UpdateTeamMemberResponse(
        user_id=uuid4(),  # Mock user ID
        account_role=request.account_role,
        updated_at=datetime.now(timezone.utc),
    )


async def remove_team_member(
    account_name: str,
    user_email: str,
    context: UserContext,
) -> None:
    """
    Remove a team member from the account.

    Mock: Returns 204 No Content.
    """
    # Authorize - owner only
    authorize_user_account(context, account_name)

    # Basic validation: prevent self-removal if last owner
    if context.email == user_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself if you are the last owner",
            headers={"Content-Type": "application/json"},
        )

    # Success - no content returned (204)
    return None


# ============================================================================
# INVITATION FLOW ENDPOINTS
# ============================================================================


async def get_invitation_details(
    token: str,
) -> InvitationDetailsResponse:
    """
    Get invitation details by token (public endpoint, no auth).

    Mock: Returns mock invitation details.
    """
    # Mock invitation details
    return InvitationDetailsResponse(
        account_name="Mock Account",
        invited_by="mock@example.com",
        role=UserRole.MANAGER,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        status=InvitationStatus.PENDING,
    )


async def accept_invitation(
    request: AcceptInvitationRequest,
    context: UserContext,
) -> AcceptInvitationResponse:
    """
    Accept an invitation and join the account.

    Mock: Returns success response with mock account details.
    """
    # Mock successful acceptance
    mock_account_id = uuid4()

    return AcceptInvitationResponse(
        account_id=mock_account_id,
        account_name="Mock Account",
        account_role=UserRole.MANAGER,
        message="Successfully joined account",
    )


async def resend_invitation(
    account_name: str,
    invitation_id: UUID,
    context: UserContext,
) -> ResendInvitationResponse:
    """
    Resend invitation email.

    Mock: Returns success message.
    """
    # Authorize - owner only
    authorize_user_account(context, account_name)

    return ResendInvitationResponse(
        message="Invitation email resent successfully",
        invitation_id=invitation_id,
    )


# ============================================================================
# MULTI-ACCOUNT SUPPORT ENDPOINTS
# ============================================================================


async def list_user_accounts(
    context: UserContext,
) -> UserAccountsListResponse:
    """
    List all accounts the user has access to.

    Mock: Returns single mock account.
    """
    # Return mock account based on user's context
    accounts = []

    # Add accounts from user's account_names
    for account_name in context.account_names:
        accounts.append(
            UserAccountResponse(
                account_id=uuid4(),
                account_name=account_name,
                role=(
                    UserRole.OWNER
                    if context.role.value == "Admin"
                    else UserRole.MANAGER
                ),
                last_accessed=datetime.now(timezone.utc),
            )
        )

    return UserAccountsListResponse(accounts=accounts)


async def switch_account(
    request: SwitchAccountRequest,
    context: UserContext,
) -> SwitchAccountResponse:
    """
    Switch active account context.

    Mock: Returns account details (backend is stateless, this is for FE).
    """
    # Mock account details
    return SwitchAccountResponse(
        account_id=request.account_id,
        account_name="Mock Account",
        role=UserRole.MANAGER,
    )
