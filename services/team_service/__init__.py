"""
Team service for RBAC team management.

This service provides team member invitation, management, and multi-account support.
All functions follow the repository pattern and return database models.

Public API:
- create_invitation: Invite a new team member
- list_team_members: List all team members with roles
- update_member_role: Update a team member's role
- remove_team_member: Remove a team member from account
- get_invitation_details: Get invitation details by token
- accept_invitation: Accept invitation and join account
- resend_invitation: Resend invitation email
- list_user_accounts: List all accounts user has access to
- validate_account_access: Validate user access to account
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from services.auth_types import UserContext

from . import _implementation
from .schema import (
    AcceptInvitationParams,
    InvitationParams,
    SwitchAccountParams,
    TeamMemberFilters,
    UpdateMemberRoleParams,
)

# ============================================================================
# TEAM MANAGEMENT
# ============================================================================


def create_invitation(
    session: Session,
    context: UserContext,
    account_name: str,
    params: InvitationParams,
) -> db.UserInvitation:
    """
    Create a new team member invitation with specified role.

    Generates a secure invitation token and creates an invitation record.
    The invitation will expire in 7 days.

    Args:
        session: Database session for the transaction.
        context: User context for audit logging.
        account_name: Name of the account to invite member to.
        params: Invitation parameters containing email and account role.

    Returns:
        db.UserInvitation: The created invitation record with token and expiration.

    Raises:
        ValueError: If account not found or duplicate pending invitation exists.

    Example:
        >>> invitation = create_invitation(
        ...     session, context, "acme-corp",
        ...     InvitationParams(email="user@example.com", account_role="manager")
        ... )
    """
    return _implementation.create_invitation(session, context, account_name, params)


def list_team_members(
    session: Session,
    account_name: str,
    filters: TeamMemberFilters,
) -> tuple[
    list[db.AccountUser],
    list[str | None],
    list[str],
    list[str],
    list[db.UserInvitation],
]:
    """
    List all team members for an account with their roles and metadata.

    Retrieves all account users and their assigned roles, with optional filtering
    by role, status, and search term. Also returns pending invitations.

    Args:
        session: Database session for the query.
        account_name: Name of the account to list members for.
        filters: Filters for role, status, and search term.

    Returns:
        Tuple containing:
        - list[db.AccountUser]: Account user records
        - list[str | None]: Account roles for each user
        - list[str]: Email addresses from account_users table
        - list[str]: Display names from account_users table
        - list[db.UserInvitation]: Pending invitations for the account

    Raises:
        ValueError: If account not found.

    Example:
        >>> users, roles, emails, names, invitations = list_team_members(
        ...     session, "acme-corp",
        ...     TeamMemberFilters(role="owner", status="active")
        ... )
    """
    return _implementation.list_team_members(session, account_name, filters)


def update_member_role(
    session: Session,
    context: UserContext,
    account_name: str,
    user_email: str,
    params: UpdateMemberRoleParams,
) -> tuple[UUID, datetime]:
    """
    Update a team member's role within the account.

    Changes the member's account-level role and invalidates relevant caches.
    Enforces last owner protection - cannot remove the last owner.

    Args:
        session: Database session for the transaction.
        context: User context for audit logging.
        account_name: Name of the account.
        user_email: Email of the user to update.
        params: Update parameters containing new account role.

    Returns:
        Tuple of (user_id, updated_at timestamp).

    Raises:
        ValueError: If account/user not found or last owner protection triggered.

    Example:
        >>> user_id, updated_at = update_member_role(
        ...     session, context, "acme-corp", "user@example.com",
        ...     UpdateMemberRoleParams(account_role="viewer")
        ... )
    """
    return _implementation.update_member_role(
        session, context, account_name, user_email, params
    )


def remove_team_member(
    session: Session,
    context: UserContext,
    account_name: str,
    user_email: str,
) -> None:
    """
    Remove a team member from the account.

    Deactivates the account membership and removes all role assignments.
    Enforces last owner protection - cannot remove the last owner.

    Args:
        session: Database session for the transaction.
        context: User context for audit logging.
        account_name: Name of the account.
        user_email: Email of the user to remove.

    Raises:
        ValueError: If account/user not found or last owner protection triggered.

    Example:
        >>> remove_team_member(session, context, "acme-corp", "user@example.com")
    """
    return _implementation.remove_team_member(
        session, context, account_name, user_email
    )


# ============================================================================
# INVITATION FLOW
# ============================================================================


def get_invitation_details(
    session: Session,
    token: str,
) -> tuple[db.UserInvitation, str, str | None, str] | None:
    """
    Get invitation details by token (public endpoint, no auth required).

    Retrieves invitation information and checks expiration status.
    Automatically marks expired invitations.

    Args:
        session: Database session for the query.
        token: Invitation token from the invitation URL.

    Returns:
        Tuple of (invitation, account_name, account_display_name, inviter_email) or None if not found.
        The inviter_email contains the name or email of the person who sent the invitation.

    Example:
        >>> result = get_invitation_details(session, "abc123...")
        >>> if result:
        ...     invitation, account_name, account_display_name, inviter_email = result
    """
    return _implementation.get_invitation_details(session, token)


def accept_invitation(
    session: Session,
    context: UserContext,
    params: AcceptInvitationParams,
) -> tuple[db.Account, str]:
    """
    Accept an invitation and join the account.

    Validates the invitation, creates account membership, assigns role,
    and marks invitation as accepted.

    Args:
        session: Database session for the transaction.
        context: User context for the accepting user.
        params: Accept invitation parameters containing token.

    Returns:
        Tuple of (account, account_role).

    Raises:
        ValueError: If invitation invalid, expired, email mismatch, or already member.

    Example:
        >>> account, role = accept_invitation(
        ...     session, context,
        ...     AcceptInvitationParams(invitation_token="abc123...")
        ... )
    """
    return _implementation.accept_invitation(session, context, params)


def resend_invitation(
    session: Session,
    invitation_id: UUID,
) -> db.UserInvitation:
    """
    Resend invitation email to the invitee.

    Re-triggers the invitation email for pending invitations.

    Args:
        session: Database session for the query.
        invitation_id: ID of the invitation to resend.

    Returns:
        db.UserInvitation: The invitation record.

    Raises:
        ValueError: If invitation not found or not in pending status.

    Example:
        >>> invitation = resend_invitation(session, invitation_id)
    """
    return _implementation.resend_invitation(session, invitation_id)


# ============================================================================
# MULTI-ACCOUNT SUPPORT
# ============================================================================


def list_user_accounts(
    session: Session,
    context: UserContext,
) -> list[tuple[db.Account, str | None, datetime]]:
    """
    List all accounts the user has access to with their roles.

    Retrieves all account memberships for the current user along with
    their primary role on each account.

    Args:
        session: Database session for the query.
        context: User context for the current user.

    Returns:
        List of tuples: (account, primary_role, last_accessed).

    Example:
        >>> accounts = list_user_accounts(session, context)
        >>> for account, role, last_accessed in accounts:
        ...     print(f"{account.name}: {role}")
    """
    return _implementation.list_user_accounts(session, context)


def list_user_accounts_by_email(
    session: Session,
    user_email: str,
) -> list[tuple[db.Account, str | None, datetime]]:
    """
    List all accounts a user has access to by their email address.

    This is an admin function that allows looking up account memberships
    by user email instead of requiring authentication context.

    Args:
        session: Database session for the query.
        user_email: Email address of the user to look up.

    Returns:
        List of tuples: (account, primary_role, last_accessed).

    Raises:
        ValueError: If user not found in Cognito.

    Example:
        >>> accounts = list_user_accounts_by_email(session, "user@example.com")
        >>> for account, role, last_accessed in accounts:
        ...     print(f"{account.name}: {role}")
    """
    return _implementation.list_user_accounts_by_email(session, user_email)


def validate_account_access(
    session: Session,
    context: UserContext,
    params: SwitchAccountParams,
) -> tuple[db.Account, str]:
    """
    Validate user has access to account for account switching.

    Verifies the user has a role on the specified account. Used by
    frontend for account switching validation. Backend is stateless.

    Args:
        session: Database session for the query.
        context: User context for the current user.
        params: Switch account parameters containing account_id.

    Returns:
        Tuple of (account, primary_role).

    Raises:
        ValueError: If account not found or user doesn't have access.

    Example:
        >>> account, role = validate_account_access(
        ...     session, context,
        ...     SwitchAccountParams(account_id=account_id)
        ... )
    """
    return _implementation.validate_account_access(session, context, params)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Functions
    "create_invitation",
    "list_team_members",
    "update_member_role",
    "remove_team_member",
    "get_invitation_details",
    "accept_invitation",
    "resend_invitation",
    "list_user_accounts",
    "validate_account_access",
    # Schemas
    "InvitationParams",
    "UpdateMemberRoleParams",
    "AcceptInvitationParams",
    "SwitchAccountParams",
    "TeamMemberFilters",
]
