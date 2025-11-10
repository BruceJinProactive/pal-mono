"""
Team service implementation for Phase 3 RBAC.

This module provides business logic for:
- Team member invitation and management
- Invitation acceptance flow
- Multi-account support

All functions return database models, not API schemas.
Routes are responsible for converting to API responses.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.orm import Session

import db
from db.repositories import (
    AccountRepository,
    AccountUserRepository,
    ResourceRoleAssignmentRepository,
    UserInvitationRepository,
)
from db.repositories.resource_role_assignment_repository import ResourceType
from db.tables.types import AccountUserStatus, InvitationStatus
from services import email_service
from services.admin_service._utils import generate_password
from services.auth_types import UserContext
from services.team_service.helpers import (
    get_mock_display_name_for_user,
    get_mock_email_for_user,
    user_id_matches_email,
)
from services.team_service.schema import (
    AcceptInvitationParams,
    InvitationParams,
    SwitchAccountParams,
    TeamMemberFilters,
    UpdateMemberRoleParams,
)
from utils.log import logger

# Postmark template ID for team invitation emails
TEAM_INVITATION_TEMPLATE_ID = 42139611

# ============================================================================
# TEAM MANAGEMENT - SYNC
# ============================================================================


def create_invitation(
    session: Session,
    context: UserContext,
    account_name: str,
    params: InvitationParams,
) -> db.UserInvitation:
    """
    Create a new team member invitation.

    Steps:
    1. Get account by name
    2. Check for existing pending invitation
    3. Generate secure token
    4. Create invitation record
    5. Return invitation

    Args:
        session: Database session
        context: User context for audit logging
        account_name: Name of the account
        params: Invitation parameters (email, role)

    Returns:
        db.UserInvitation: Created invitation record

    Raises:
        ValueError: If account not found or duplicate invitation exists
    """
    # 1. Get account
    account_repo = AccountRepository(session)
    account = account_repo.get_account(account_name)
    if not account:
        raise ValueError(f"Account '{account_name}' not found")

    # 2. Check for existing pending invitation
    invitation_repo = UserInvitationRepository(session)
    pending_invitations = invitation_repo.get_pending_for_account(account.id)
    for inv in pending_invitations:
        if inv.email.lower() == params.email.lower():
            raise ValueError("Pending invitation already exists for this email")

    # 3. Generate secure token
    invitation_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    # 4. Create Cognito user with temporary password
    user_name = params.email.split("@")[0].replace(".", " ").title()
    password = generate_password()

    # Get AWS configuration
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    user_pool_id = os.environ.get("AWS_ADMIN_CONSOLE_USER_POOL_ID")

    cognito_user_created = False
    if user_pool_id:
        try:
            cognito_client = boto3.client("cognito-idp", region_name=aws_region)
            cognito_client.admin_create_user(
                UserPoolId=user_pool_id,
                Username=params.email,
                TemporaryPassword=password,
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": params.email},
                    {"Name": "email_verified", "Value": "true"},
                    {"Name": "name", "Value": user_name},
                    {"Name": "custom:account_name", "Value": account.name},
                ],
            )
            cognito_user_created = True
            logger.info(f"Created Cognito user for invitation: {params.email}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "UsernameExistsException":
                # User already exists in Cognito, that's okay
                cognito_user_created = False
                logger.info(f"Cognito user already exists: {params.email}")
            else:
                logger.error(f"Failed to create Cognito user for invitation: {e}")
                # Continue with invitation creation even if Cognito user creation fails

    # 5. Create invitation record
    try:
        invitation = invitation_repo.create(
            account_id=account.id,
            email=params.email,
            account_role=params.account_role,
            invited_by=UUID(context.username),
            invitation_token=invitation_token,
            expires_at=expires_at,
        )
    except Exception as e:
        raise ValueError(f"Failed to create invitation: {str(e)}")

    # 6. Send invitation email
    try:
        # Get inviter name for personalization
        inviter_name = context.display_name or "A team member"
        account_display_name = account.display_name or account.name

        template_model = {
            "name": user_name,
            "inviter_name": inviter_name,
            "account_name": account_display_name,
            "role": params.account_role,
            "product_name": "Palona AI",
            "sender_name": "Support Team",
        }

        # Construct base URL based on environment
        base_url = (
            "https://console.palona.ai"
            if os.getenv("RUNTIME_ENV", "prd") == "prd"
            else f"https://{os.getenv('RUNTIME_ENV', 'lat')}-console.palona.ai"
        )
        template_model["invitation_url"] = (
            f"{base_url}/accept-invitation?token={invitation_token}"
        )

        # Include password if Cognito user was created
        if cognito_user_created:
            template_model["password"] = password
            template_model["email"] = params.email
            template_model["login_url"] = f"{base_url}/signin?email={params.email}"

        email_service.send_email_with_template(
            to_email=params.email,
            template_id=TEAM_INVITATION_TEMPLATE_ID,
            template_model=template_model,
        )
        logger.info(
            f"Invitation email sent to {params.email} for account {account.name}"
        )
    except Exception as e:
        logger.error(f"Failed to send invitation email to {params.email}: {e}")
        # Don't fail the invitation creation if email fails
        # The invitation is still valid and can be resent

    return invitation


def list_team_members(
    session: Session,
    account_name: str,
    filters: TeamMemberFilters,
) -> tuple[list[db.AccountUser], list[str | None], list[str], list[str]]:
    """
    List all team members for an account with their roles.

    Steps:
    1. Get account by name
    2. Get all account users (with optional status filter)
    3. For each user, get their role
    4. Apply filters (role, search)
    5. Return account users and their metadata

    Args:
        session: Database session
        account_name: Name of the account
        filters: Filters for role, status, and search

    Returns:
        Tuple of:
        - list[db.AccountUser]: Account user records
        - list[str | None]: Account roles for each user
        - list[str]: Emails for each user (mock data)
        - list[str]: Display names for each user (mock data)

    Raises:
        ValueError: If account not found
    """
    # 1. Get account
    account_repo = AccountRepository(session)
    account = account_repo.get_account(account_name)
    if not account:
        raise ValueError(f"Account '{account_name}' not found")

    # 2. Get all account users
    account_user_repo = AccountUserRepository(session)
    status_filter = AccountUserStatus(filters.status) if filters.status else None
    account_users = account_user_repo.get_users_for_account(
        account.id, status=status_filter
    )

    # 3. For each user, get their role and build lists
    role_repo = ResourceRoleAssignmentRepository(session)
    filtered_users = []
    roles = []
    emails = []
    names = []

    for au in account_users:
        # Get roles for this user on this account
        user_roles = role_repo.get_roles_for_resource(
            au.user_id, ResourceType.ACCOUNT, account.id
        )

        # Get primary account role (first owner, else manager, else viewer)
        account_role = None
        for r in ["owner", "manager", "viewer"]:
            if r in user_roles:
                account_role = r
                break

        # Apply role filter
        if filters.role and (not account_role or account_role != filters.role):
            continue

        # Get email and name (mock for now - TODO: get from account_users.email)
        member_email = get_mock_email_for_user(au.user_id)
        member_name = get_mock_display_name_for_user(au.user_id)

        # Apply search filter
        if filters.search and filters.search.lower() not in member_email.lower():
            continue

        filtered_users.append(au)
        roles.append(account_role)
        emails.append(member_email)
        names.append(member_name)

    return filtered_users, roles, emails, names


def update_member_role(
    session: Session,
    context: UserContext,
    account_name: str,
    user_email: str,
    params: UpdateMemberRoleParams,
) -> tuple[UUID, datetime]:
    """
    Update a team member's role.

    Steps:
    1. Get account
    2. Find user by email (mock: only works for current user)
    3. Get current role
    4. Check last owner protection
    5. Remove old role and add new role
    6. Invalidate cache
    7. Return user_id and timestamp

    Args:
        session: Database session
        context: User context for audit logging
        account_name: Name of the account
        user_email: Email of the user to update
        params: Update parameters (new role)

    Returns:
        Tuple of (user_id, updated_at timestamp)

    Raises:
        ValueError: If account/user not found or last owner protection triggered
    """
    # 1. Get account
    account_repo = AccountRepository(session)
    account = account_repo.get_account(account_name)
    if not account:
        raise ValueError(f"Account '{account_name}' not found")

    # 2. Find user by email (mock: only current user for now)
    # TODO: Once email is in account_users, query by email
    account_user_repo = AccountUserRepository(session)
    account_users = account_user_repo.get_users_for_account(account.id)

    target_user_id = None
    for au in account_users:
        if user_id_matches_email(au.user_id, user_email, context.email):
            target_user_id = au.user_id
            break

    if not target_user_id:
        raise ValueError("User not found in account")

    # 3. Get current role
    role_repo = ResourceRoleAssignmentRepository(session)
    current_roles = role_repo.get_roles_for_resource(
        target_user_id, ResourceType.ACCOUNT, account.id
    )
    current_role = current_roles[0] if current_roles else None

    # 4. Check last owner protection
    if current_role == "owner" and params.account_role != "owner":
        owner_count = role_repo.count_owners_for_resource(
            ResourceType.ACCOUNT, account.id
        )
        if owner_count <= 1:
            raise ValueError("Cannot remove the last owner from the account")

    # 5. Remove old role and add new role
    if current_role:
        role_repo.remove_role(
            target_user_id, ResourceType.ACCOUNT, account.id, current_role
        )

    role_repo.add_role(
        user_id=target_user_id,
        resource_type=ResourceType.ACCOUNT,
        resource_id=account.id,
        role=params.account_role,
        assigned_by=UUID(context.username),
        reason="Role updated via API",
    )

    # 6. Send notification email (TODO)

    # 7. Return user_id and timestamp
    updated_at = datetime.now(timezone.utc)
    return target_user_id, updated_at


def remove_team_member(
    session: Session,
    context: UserContext,
    account_name: str,
    user_email: str,
) -> None:
    """
    Remove a team member from the account.

    Steps:
    1. Get account
    2. Find user by email (mock: only works for current user)
    3. Check last owner protection
    4. Deactivate AccountUser record
    5. Remove all role assignments
    6. Invalidate cache

    Args:
        session: Database session
        context: User context for audit logging
        account_name: Name of the account
        user_email: Email of the user to remove

    Raises:
        ValueError: If account/user not found or last owner protection triggered
    """
    # 1. Get account
    account_repo = AccountRepository(session)
    account = account_repo.get_account(account_name)
    if not account:
        raise ValueError(f"Account '{account_name}' not found")

    # 2. Find user by email (mock: only current user for now)
    account_user_repo = AccountUserRepository(session)
    account_users = account_user_repo.get_users_for_account(account.id)

    target_user_id = None
    for au in account_users:
        if user_id_matches_email(au.user_id, user_email, context.email):
            target_user_id = au.user_id
            break

    if not target_user_id:
        raise ValueError("User not found in account")

    # 3. Check last owner protection
    role_repo = ResourceRoleAssignmentRepository(session)
    current_roles = role_repo.get_roles_for_resource(
        target_user_id, ResourceType.ACCOUNT, account.id
    )

    if "owner" in current_roles:
        owner_count = role_repo.count_owners_for_resource(
            ResourceType.ACCOUNT, account.id
        )
        if owner_count <= 1:
            raise ValueError("Cannot remove the last owner from the account")

    # 4. Deactivate AccountUser record
    account_user_repo.update_status(
        target_user_id, account.id, AccountUserStatus.deactivated
    )

    # 5. Remove all role assignments
    role_repo.remove_all_roles_for_user_on_resource(
        target_user_id, ResourceType.ACCOUNT, account.id
    )

    # 6. Send notification email (TODO)


# ============================================================================
# INVITATION FLOW - SYNC
# ============================================================================


def get_invitation_details(
    session: Session,
    token: str,
) -> tuple[db.UserInvitation, str, str] | None:
    """
    Get invitation details by token (public endpoint, no auth).

    Steps:
    1. Get invitation by token
    2. Check if expired and mark if so
    3. Get account name
    4. Get inviter's email/name
    5. Return invitation, account name, and inviter info

    Args:
        session: Database session
        token: Invitation token

    Returns:
        Tuple of (invitation, account_name, inviter_email) or None if not found
    """
    # 1. Get invitation by token
    invitation_repo = UserInvitationRepository(session)
    invitation = invitation_repo.get_by_token(token)
    if not invitation:
        return None

    # 2. Check if expired and mark if so
    now = datetime.now(timezone.utc)
    if invitation.status == InvitationStatus.pending and invitation.expires_at < now:
        invitation_repo.mark_as_expired(invitation.id)
        invitation.status = InvitationStatus.expired

    # 3. Get account
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(invitation.account_id)
    account_name = account.name if account else "Unknown Account"

    # 4. Get inviter's email/name from account_users
    inviter_email = "Unknown User"
    account_user_repo = AccountUserRepository(session)
    inviter_account_user = account_user_repo.get_by_user_and_account(
        invitation.invited_by, invitation.account_id
    )
    if inviter_account_user:
        # Use name if available, otherwise use email, otherwise use "Unknown User"
        if inviter_account_user.name:
            inviter_email = inviter_account_user.name
        elif inviter_account_user.email:
            inviter_email = inviter_account_user.email

    return invitation, account_name, inviter_email


def accept_invitation(
    session: Session,
    context: UserContext,
    params: AcceptInvitationParams,
) -> tuple[db.Account, str]:
    """
    Accept an invitation and join the account.

    Steps:
    1. Get invitation by token
    2. Validate invitation (pending status, not expired, email matches)
    3. Get account
    4. Check not already a member
    5. Create AccountUser record (membership)
    6. Create ResourceRoleAssignment record (role)
    7. Mark invitation as accepted
    8. Clear cache
    9. Return account and role

    Args:
        session: Database session
        context: User context
        params: Accept invitation parameters (token)

    Returns:
        Tuple of (account, account_role)

    Raises:
        ValueError: If invitation invalid, expired, email mismatch, or already member
    """
    # 1. Get invitation by token
    invitation_repo = UserInvitationRepository(session)
    invitation = invitation_repo.get_by_token(params.invitation_token)
    if not invitation:
        raise ValueError("Invitation not found")

    # 2. Validate invitation
    if invitation.status != InvitationStatus.pending:
        raise ValueError(f"Invitation is {invitation.status.value}")

    now = datetime.now(timezone.utc)
    if invitation.expires_at < now:
        invitation_repo.mark_as_expired(invitation.id)
        raise ValueError("Invitation has expired")

    if invitation.email.lower() != context.email.lower():
        raise ValueError("Email does not match invitation")

    # 3. Get account
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(invitation.account_id)
    if not account:
        raise ValueError("Account not found")

    # 4. Check not already a member
    account_user_repo = AccountUserRepository(session)
    user_id = UUID(context.username)
    if account_user_repo.is_member(user_id, account.id):
        raise ValueError("Already a member of this account")

    # 5. Create account membership
    try:
        account_user_repo.create(
            account_id=account.id,
            user_id=user_id,
            email=context.email,
            name=context.display_name,
            added_by=invitation.invited_by,
            status=AccountUserStatus.active,
        )
    except Exception as e:
        raise ValueError(f"Failed to create account membership: {str(e)}")

    # 6. Assign role
    role_repo = ResourceRoleAssignmentRepository(session)
    try:
        role_repo.add_role(
            user_id=user_id,
            resource_type=ResourceType.ACCOUNT,
            resource_id=account.id,
            role=invitation.account_role,
            assigned_by=invitation.invited_by,
            reason="Accepted invitation",
        )
    except Exception as e:
        raise ValueError(f"Failed to assign role: {str(e)}")

    # 7. Mark invitation as accepted
    try:
        invitation_repo.mark_as_accepted(invitation.id)
    except Exception as e:
        logger.error(f"Failed to mark invitation as accepted: {e}")

    # 8. Return account and role
    return account, invitation.account_role


def resend_invitation(
    session: Session,
    invitation_id: UUID,
) -> db.UserInvitation:
    """
    Resend invitation email.

    Steps:
    1. Get invitation
    2. Validate invitation is pending
    3. Resend email (TODO)
    4. Return invitation

    Args:
        session: Database session
        invitation_id: ID of the invitation

    Returns:
        db.UserInvitation: The invitation record

    Raises:
        ValueError: If invitation not found or not pending
    """
    # 1. Get invitation
    invitation_repo = UserInvitationRepository(session)
    invitation = invitation_repo.get_by_id(invitation_id)
    if not invitation:
        raise ValueError("Invitation not found")

    # 2. Validate invitation is pending
    if invitation.status != InvitationStatus.pending:
        raise ValueError(
            f"Cannot resend invitation with status {invitation.status.value}"
        )

    # 3. Resend email (TODO)
    # try:
    #     send_invitation_email(...)
    # except Exception as e:
    #     logger.error(f"Failed to resend invitation email: {e}")
    #     raise ValueError("Failed to send email")

    return invitation


# ============================================================================
# MULTI-ACCOUNT SUPPORT - SYNC
# ============================================================================


def list_user_accounts(
    session: Session,
    context: UserContext,
) -> list[tuple[db.Account, str | None, datetime]]:
    """
    List all accounts the user has access to.

    Steps:
    1. Get all account memberships for current user
    2. For each membership, get account details and role
    3. Return list of (account, role, last_accessed) tuples

    Args:
        session: Database session
        context: User context

    Returns:
        List of tuples: (account, primary_role, last_accessed)
    """
    # 1. Get all account memberships for current user
    account_user_repo = AccountUserRepository(session)
    user_id = UUID(context.username)
    account_memberships = account_user_repo.get_accounts_for_user(user_id)

    # 2. For each membership, get account details and role
    account_repo = AccountRepository(session)
    role_repo = ResourceRoleAssignmentRepository(session)
    result = []

    for membership in account_memberships:
        account = account_repo.get_account_by_id(membership.account_id)
        if not account:
            continue

        # Get user's role on this account
        user_roles = role_repo.get_roles_for_resource(
            user_id, ResourceType.ACCOUNT, account.id
        )

        # Get primary role
        primary_role = None
        for r in ["owner", "manager", "viewer"]:
            if r in user_roles:
                primary_role = r
                break

        # TODO: Track actual last access
        last_accessed = membership.added_at

        result.append((account, primary_role, last_accessed))

    return result


def validate_account_access(
    session: Session,
    context: UserContext,
    params: SwitchAccountParams,
) -> tuple[db.Account, str]:
    """
    Validate user has access to account and return account with role.

    This is used for account switching validation. Backend is stateless -
    this validates user has access and returns account info for frontend.

    Args:
        session: Database session
        context: User context
        params: Switch account parameters (account_id)

    Returns:
        Tuple of (account, primary_role)

    Raises:
        ValueError: If account not found or user doesn't have access
    """
    # Get account to validate it exists
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(params.account_id)
    if not account:
        raise ValueError("Account not found")

    # Get user's role on this account
    role_repo = ResourceRoleAssignmentRepository(session)
    user_id = UUID(context.username)
    user_roles = role_repo.get_roles_for_resource(
        user_id, ResourceType.ACCOUNT, account.id
    )

    # Get primary role
    primary_role = None
    for r in ["owner", "manager", "viewer"]:
        if r in user_roles:
            primary_role = r
            break

    if not primary_role:
        raise ValueError("User does not have access to this account")

    return account, primary_role


# ============================================================================
# ASYNC VARIANTS
# ============================================================================

# TODO: Implement async variants of all functions above
# Follow pattern: async def function_name_async(session: AsyncSession, ...)
#
# async def create_invitation_async(...)
# async def list_team_members_async(...)
# async def update_member_role_async(...)
# async def remove_team_member_async(...)
# async def get_invitation_details_async(...)
# async def accept_invitation_async(...)
# async def resend_invitation_async(...)
# async def list_user_accounts_async(...)
# async def validate_account_access_async(...)
