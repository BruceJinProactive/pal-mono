"""
Team management route handlers for Phase 3 RBAC.

This module provides route handlers for:
- Team member invitation and management
- Invitation acceptance flow
- Multi-account support

All business logic has been moved to services/team_service.
Route handlers focus on authorization, service calls, and response conversion.
"""

from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.orm import Session

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
    TeamMemberResponse,
    TeamMembersListResponse,
    UpdateTeamMemberRequest,
    UpdateTeamMemberResponse,
    UserAccountResponse,
    UserAccountsListResponse,
    UserRole,
)
from services import team_service
from services.team_service.schema import (
    AcceptInvitationParams,
    InvitationParams,
    SwitchAccountParams,
    TeamMemberFilters,
    UpdateMemberRoleParams,
)

# ============================================================================
# TEAM MANAGEMENT ENDPOINTS
# ============================================================================


async def invite_team_member(
    account_name: str,
    request: InviteTeamMemberRequest,
    context: UserContext,
    session: Session,
) -> InvitationResponse:
    """
    Invite a new team member with specified role.

    Route handler that:
    1. Authorizes user is owner
    2. Calls team service to create invitation
    3. Converts DB model to API response
    """
    # 1. Authorize - owner only (TODO: check actual owner role via RBAC)
    authorize_user_account(context, account_name)

    # 2. Call service to create invitation
    try:
        invitation = team_service.create_invitation(
            session=session,
            context=context,
            account_name=account_name,
            params=InvitationParams(
                email=request.email,
                account_role=request.account_role.value,
            ),
        )
    except ValueError as e:
        # Convert business logic errors to HTTP exceptions
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(e),
                headers={"Content-Type": "application/json"},
            )
        else:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(e),
                headers={"Content-Type": "application/json"},
            )

    # 3. Convert DB model to API response
    api_status = InvitationStatus[invitation.status.name.upper()]

    return InvitationResponse(
        invitation_id=invitation.id,
        email=invitation.email,
        account_role=UserRole(invitation.account_role),
        invitation_token=invitation.invitation_token,
        expires_at=invitation.expires_at,
        status=api_status,
    )


async def list_team_members(
    account_name: str,
    context: UserContext,
    session: Session,
    role: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> TeamMembersListResponse:
    """
    List all team members for an account.

    Route handler that:
    1. Authorizes user has access to account
    2. Calls team service to list members
    3. Converts DB models to API response
    """
    # 1. Authorize - any authenticated user with account access
    authorize_user_account(context, account_name)

    # 2. Call service to list team members
    try:
        account_users, roles, emails, names = team_service.list_team_members(
            session=session,
            account_name=account_name,
            filters=TeamMemberFilters(role=role, status=status, search=search),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    # 3. Convert DB models to API response
    members = []
    for au, account_role, member_email, member_name in zip(
        account_users, roles, emails, names
    ):
        # If this is the current user, use their real email and name
        if str(au.user_id) == context.username:
            member_email = context.email
            member_name = context.display_name

        members.append(
            TeamMemberResponse(
                user_id=au.user_id,
                email=member_email,
                name=member_name,
                account_role=UserRole(account_role) if account_role else None,
                status=au.status.value,
                added_at=au.added_at,
                last_active=None,  # TODO: Track last_active
                resource_roles=[],  # V2 feature
            )
        )

    return TeamMembersListResponse(
        members=members,
        total=len(members),
    )


async def update_team_member_role(
    account_name: str,
    user_email: str,
    request: UpdateTeamMemberRequest,
    context: UserContext,
    session: Session,
) -> UpdateTeamMemberResponse:
    """
    Update a team member's role.

    Route handler that:
    1. Authorizes user is owner
    2. Calls team service to update role
    3. Converts result to API response
    """
    # 1. Authorize - owner only
    authorize_user_account(context, account_name)

    # 2. Call service to update member role
    try:
        user_id, updated_at = team_service.update_member_role(
            session=session,
            context=context,
            account_name=account_name,
            user_email=user_email,
            params=UpdateMemberRoleParams(account_role=request.account_role.value),
        )
    except ValueError as e:
        # Convert business logic errors to HTTP exceptions
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(e),
                headers={"Content-Type": "application/json"},
            )
        else:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(e),
                headers={"Content-Type": "application/json"},
            )

    # 3. Return API response
    return UpdateTeamMemberResponse(
        user_id=user_id,
        account_role=request.account_role,
        updated_at=updated_at,
    )


async def remove_team_member(
    account_name: str,
    user_email: str,
    context: UserContext,
    session: Session,
) -> None:
    """
    Remove a team member from the account.

    Route handler that:
    1. Authorizes user is owner
    2. Calls team service to remove member
    3. Returns 204 No Content
    """
    # 1. Authorize - owner only
    authorize_user_account(context, account_name)

    # 2. Call service to remove team member
    try:
        team_service.remove_team_member(
            session=session,
            context=context,
            account_name=account_name,
            user_email=user_email,
        )
    except ValueError as e:
        # Convert business logic errors to HTTP exceptions
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(e),
                headers={"Content-Type": "application/json"},
            )
        else:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(e),
                headers={"Content-Type": "application/json"},
            )

    # 3. Return 204 No Content
    return None


# ============================================================================
# INVITATION FLOW ENDPOINTS
# ============================================================================


async def get_invitation_details(
    token: str,
    session: Session,
) -> InvitationDetailsResponse:
    """
    Get invitation details by token (public endpoint, no auth).

    Route handler that:
    1. Calls team service to get invitation details
    2. Converts DB model to API response
    """
    # 1. Call service to get invitation details
    result = team_service.get_invitation_details(session=session, token=token)
    if not result:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
            headers={"Content-Type": "application/json"},
        )

    invitation, account_name, inviter_email = result

    # 2. Convert DB model to API response
    api_status = InvitationStatus[invitation.status.name.upper()]

    return InvitationDetailsResponse(
        account_name=account_name,
        invited_by=inviter_email,
        role=UserRole(invitation.account_role),
        expires_at=invitation.expires_at,
        status=api_status,
    )


async def accept_invitation(
    request: AcceptInvitationRequest,
    context: UserContext,
    session: Session,
) -> AcceptInvitationResponse:
    """
    Accept an invitation and join the account.

    Route handler that:
    1. Calls team service to accept invitation
    2. Converts DB model to API response
    """
    # 1. Call service to accept invitation
    try:
        account, account_role = team_service.accept_invitation(
            session=session,
            context=context,
            params=AcceptInvitationParams(invitation_token=request.invitation_token),
        )
    except ValueError as e:
        # Convert business logic errors to HTTP exceptions
        error_msg = str(e).lower()
        if "not found" in error_msg:
            status_code = http_status.HTTP_404_NOT_FOUND
        else:
            status_code = http_status.HTTP_400_BAD_REQUEST

        raise HTTPException(
            status_code=status_code,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    # 2. Return API response
    return AcceptInvitationResponse(
        account_id=account.id,
        account_name=account.name,
        account_role=UserRole(account_role),
        message="Successfully joined account",
    )


async def resend_invitation(
    account_name: str,
    invitation_id: UUID,
    context: UserContext,
    session: Session,
) -> ResendInvitationResponse:
    """
    Resend invitation email.

    Route handler that:
    1. Authorizes user is owner
    2. Calls team service to resend invitation
    3. Returns success message
    """
    # 1. Authorize - owner only
    authorize_user_account(context, account_name)

    # 2. Call service to resend invitation
    try:
        team_service.resend_invitation(session=session, invitation_id=invitation_id)
    except ValueError as e:
        # Convert business logic errors to HTTP exceptions
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(e),
                headers={"Content-Type": "application/json"},
            )
        else:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=str(e),
                headers={"Content-Type": "application/json"},
            )

    # 3. Return success message
    return ResendInvitationResponse(
        message="Invitation email resent successfully",
        invitation_id=invitation_id,
    )


# ============================================================================
# MULTI-ACCOUNT SUPPORT ENDPOINTS
# ============================================================================


async def list_user_accounts(
    context: UserContext,
    session: Session,
) -> UserAccountsListResponse:
    """
    List all accounts the user has access to.

    Route handler that:
    1. Calls team service to list user accounts
    2. Converts DB models to API response
    """
    # 1. Call service to list user accounts
    account_data = team_service.list_user_accounts(session=session, context=context)

    # 2. Convert DB models to API response
    accounts = []
    for account, primary_role, last_accessed in account_data:
        accounts.append(
            UserAccountResponse(
                account_id=account.id,
                account_name=account.name,
                role=UserRole(primary_role) if primary_role else None,
                last_accessed=last_accessed,
            )
        )

    return UserAccountsListResponse(accounts=accounts)


async def switch_account(
    request: SwitchAccountRequest,
    context: UserContext,
    session: Session,
) -> SwitchAccountResponse:
    """
    Switch active account context.

    Backend is stateless - this validates user has access and returns account info.
    Frontend uses this for state management.

    Route handler that:
    1. Calls team service to validate account access
    2. Converts DB model to API response
    """
    # 1. Call service to validate account access
    try:
        account, primary_role = team_service.validate_account_access(
            session=session,
            context=context,
            params=SwitchAccountParams(account_id=request.account_id),
        )
    except ValueError as e:
        # Convert business logic errors to HTTP exceptions
        error_msg = str(e).lower()
        if "not found" in error_msg:
            status_code = http_status.HTTP_404_NOT_FOUND
        elif "access" in error_msg or "permission" in error_msg:
            status_code = http_status.HTTP_403_FORBIDDEN
        else:
            status_code = http_status.HTTP_400_BAD_REQUEST

        raise HTTPException(
            status_code=status_code,
            detail=str(e),
            headers={"Content-Type": "application/json"},
        )

    # 2. Return API response
    return SwitchAccountResponse(
        account_id=account.id,
        account_name=account.name,
        role=UserRole(primary_role),
    )
