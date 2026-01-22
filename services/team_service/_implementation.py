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
from services.auth_types import UserContext, UserRole
from services.team_service.invitation_token import generate_invitation_jwt
from services.team_service.schema import (
    AcceptInvitationParams,
    InvitationParams,
    SwitchAccountParams,
    TeamMemberFilters,
    UpdateMemberRoleParams,
)
from utils.log import logger

AWS_REGION = os.environ["AWS_REGION"]
AWS_ADMIN_CONSOLE_USER_POOL_ID = os.environ["AWS_ADMIN_CONSOLE_USER_POOL_ID"]

# Postmark template IDs for team invitation emails
TEAM_INVITATION_NEW_USER_TEMPLATE_ID = 42139611  # For new users (with password)
TEAM_INVITATION_EXISTING_USER_TEMPLATE_ID = 42173053  # For existing confirmed users
TEAM_INVITATION_PENDING_USER_TEMPLATE_ID = 42173054  # For users who never logged in

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_cognito_user_status(
    email: str, user_pool_id: str, aws_region: str
) -> tuple[bool, str | None]:
    """
    Check if a user exists in Cognito and return their status.

    Args:
        email: User's email address
        user_pool_id: Cognito User Pool ID
        aws_region: AWS region

    Returns:
        tuple[bool, str | None]: (user_exists, user_status)
        - user_exists: True if user exists in Cognito
        - user_status: Cognito user status (FORCE_CHANGE_PASSWORD, CONFIRMED, etc.) or None
    """
    try:
        cognito_client = boto3.client("cognito-idp", region_name=aws_region)
        response = cognito_client.admin_get_user(
            UserPoolId=user_pool_id,
            Username=email,
        )
        user_status = response.get("UserStatus")
        logger.info(f"Found existing Cognito user: {email} with status: {user_status}")
        return True, user_status
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "UserNotFoundException":
            logger.info(f"Cognito user not found: {email}")
            return False, None
        else:
            logger.error(f"Error checking Cognito user status: {e}")
            raise  # Re-raise to surface AWS issues to caller


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
    2. Check if user is already a member of the account
    3. Check for existing pending invitation
    4. Generate secure token
    5. Check Cognito user status and create if needed
    6. Create invitation record
    7. Send invitation email
    8. Return invitation

    Args:
        session: Database session
        context: User context for audit logging
        account_name: Name of the account
        params: Invitation parameters (email, role)

    Returns:
        db.UserInvitation: Created invitation record

    Raises:
        ValueError: If account not found, user is already a member, or duplicate invitation exists
    """
    # 1. Get account
    account_repo = AccountRepository(session)
    account = account_repo.get_account(account_name)
    if not account:
        raise ValueError(f"Account '{account_name}' not found")

    # 2. Check if user is already a member of the account
    account_user_repo = AccountUserRepository(session)
    existing_member = account_user_repo.get_by_email_and_account(
        params.email, account.id
    )
    if existing_member:
        raise ValueError("User is already a member of this account")

    # 3. Check for existing pending invitation
    invitation_repo = UserInvitationRepository(session)
    if invitation_repo.has_pending_for_email(account.id, params.email):
        raise ValueError("Pending invitation already exists for this email")

    # 4. Generate secure token
    invitation_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    # 5. Check Cognito user status and create if needed
    user_name = params.email.split("@")[0].replace(".", " ").title()
    password = generate_password()

    # Get AWS configuration
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    user_pool_id = os.environ.get("AWS_ADMIN_CONSOLE_USER_POOL_ID")

    # Check if user exists and get their status
    user_exists = False
    user_status = None
    cognito_user_created = False

    if user_pool_id:
        user_exists, user_status = get_cognito_user_status(
            params.email, user_pool_id, aws_region
        )

        # If user doesn't exist, create them
        if not user_exists:
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
                    ],
                )
                cognito_user_created = True
                user_status = "FORCE_CHANGE_PASSWORD"
                logger.info(f"Created Cognito user for invitation: {params.email}")
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "UsernameExistsException":
                    # Race condition: user was created between check and create
                    logger.warning(
                        f"Cognito user already exists (race condition): {params.email}"
                    )
                    user_exists, user_status = get_cognito_user_status(
                        params.email, user_pool_id, aws_region
                    )
                else:
                    logger.error(f"Failed to create Cognito user for invitation: {e}")
                    raise ValueError(f"Failed to create Cognito user: {error_code}")

    # 6. Create invitation record
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

    # 7. Send invitation email based on user status
    try:
        # Get inviter name for personalization
        inviter_name = context.display_name or "A team member"
        account_display_name = account.display_name or account.name

        # Base template model for all email types
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

        # Generate JWT token that includes temporary password for new users
        jwt_token = generate_invitation_jwt(
            invitation_token=invitation_token,
            email=params.email,
            temporary_password=password if cognito_user_created else None,
            expires_at=expires_at,
        )
        template_model["invitation_url"] = (
            f"{base_url}/accept-invitation?token={jwt_token}"
        )

        # Determine which email template to use based on user status
        if cognito_user_created:
            # Case 1: Brand new user - password embedded in JWT token, not in email
            template_id = TEAM_INVITATION_NEW_USER_TEMPLATE_ID
            template_model["email"] = params.email
            template_model["login_url"] = f"{base_url}/signin?email={params.email}"
            logger.info(
                f"Sending new user invitation email to {params.email} (password embedded in token)"
            )
        elif user_status == "FORCE_CHANGE_PASSWORD":
            # Case 2: User created but never logged in - resend password reset instructions
            template_id = TEAM_INVITATION_PENDING_USER_TEMPLATE_ID
            template_model["email"] = params.email
            template_model["login_url"] = f"{base_url}/signin?email={params.email}"
            template_model["reset_password_url"] = (
                f"{base_url}/forgot-password?email={params.email}"
            )
            logger.info(
                f"Sending pending user invitation email to {params.email} (never logged in)"
            )
        else:
            # Case 3: Existing confirmed user - send simpler invitation without credentials
            template_id = TEAM_INVITATION_EXISTING_USER_TEMPLATE_ID
            template_model["login_url"] = f"{base_url}/signin"
            logger.info(
                f"Sending existing user invitation email to {params.email} (already confirmed)"
            )

        email_service.send_email_with_template(
            to_email=params.email,
            template_id=template_id,
            template_model=template_model,
            bcc_emails=["notifications@palona.ai"],
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
) -> tuple[
    list[db.AccountUser],
    list[str | None],
    list[str],
    list[str],
    list[db.UserInvitation],
]:
    """
    List all team members for an account with their roles and pending invitations.

    Steps:
    1. Get account by name
    2. Get all account users (with optional status filter)
    3. For each user, get their role
    4. Apply filters (role, search)
    5. Get pending invitations for the account
    6. Return account users, their metadata, and pending invitations

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
        - list[db.UserInvitation]: Pending invitations

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

        # Get email and name from account_users table
        member_email = au.email or "unknown@example.com"
        member_name = au.name or f"User {str(au.user_id)[:8]}"

        # Apply search filter
        if filters.search and filters.search.lower() not in member_email.lower():
            continue

        filtered_users.append(au)
        roles.append(account_role)
        emails.append(member_email)
        names.append(member_name)

    # 5. Get pending invitations for the account
    invitation_repo = UserInvitationRepository(session)
    pending_invitations = invitation_repo.get_pending_for_account(account.id)

    return filtered_users, roles, emails, names, pending_invitations


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
    2. Find user by email
    3. Get current role
    4. Check idempotency (skip if role unchanged)
    5. Check last owner protection
    6. Remove old role and add new role (with transaction safety)
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
        ValueError: If account/user not found, last owner protection triggered, or role update fails
    """
    # 1. Get account
    account_repo = AccountRepository(session)
    account = account_repo.get_account(account_name)
    if not account:
        raise ValueError(f"Account '{account_name}' not found")

    # 2. Find user by email
    account_user_repo = AccountUserRepository(session)
    account_users = account_user_repo.get_users_for_account(account.id)

    target_user_id = None
    for au in account_users:
        if au.email and au.email.lower() == user_email.lower():
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

    # 4. Check idempotency - skip if role unchanged
    if current_role == params.account_role:
        logger.info(
            f"User {user_email} already has role {params.account_role} on account {account_name}, skipping update"
        )
        updated_at = datetime.now(timezone.utc)
        return target_user_id, updated_at

    # 5. Check last owner protection
    if current_role == "owner" and params.account_role != "owner":
        owner_count = role_repo.count_owners_for_resource(
            ResourceType.ACCOUNT, account.id
        )
        if owner_count <= 1:
            raise ValueError("Cannot remove the last owner from the account")

    # 6. Remove old role and add new role with transaction safety
    try:
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

        # Flush to detect any constraint violations before committing
        session.flush()

        logger.info(
            f"Updated role for user {user_email} from {current_role} to {params.account_role} on account {account_name}",
            extra={
                "user_id": str(target_user_id),
                "account_id": str(account.id),
                "old_role": current_role,
                "new_role": params.account_role,
                "updated_by": context.username,
            },
        )
    except Exception as e:
        logger.error(
            f"Failed to update role for user {user_email}: {e}",
            extra={
                "user_email": user_email,
                "account_name": account_name,
                "error": str(e),
            },
        )
        session.rollback()
        raise ValueError(f"Failed to update role: {str(e)}")

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
    Remove a team member from the account or revoke a pending invitation.

    Steps:
    1. Get account
    2. Check for pending invitation first
    3. If no pending invitation, find confirmed user by email
    4. Check last owner protection (for confirmed users)
    5. Deactivate AccountUser record or revoke invitation
    6. Remove all role assignments (for confirmed users)

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

    # 2. Check for pending invitation first
    invitation_repo = UserInvitationRepository(session, auto_commit=True)
    pending_invitations = invitation_repo.get_pending_for_account(account.id)

    # Find matching invitation by email
    matching_invitation = None
    for invitation in pending_invitations:
        if invitation.email.lower() == user_email.lower():
            matching_invitation = invitation
            break

    # If there's a pending invitation, revoke it and return
    if matching_invitation:
        invitation_repo.revoke(matching_invitation.id)
        logger.info(
            f"Revoked pending invitation for {user_email} in account {account_name}"
        )
        return

    # 3. Find confirmed user by email
    account_user_repo = AccountUserRepository(session)
    account_users = account_user_repo.get_users_for_account(account.id)

    target_user_id = None
    for au in account_users:
        if au.email and au.email.lower() == user_email.lower():
            target_user_id = au.user_id
            break

    if not target_user_id:
        raise ValueError("User not found in account")

    # 4. Check last owner protection
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

    # 5. Deactivate AccountUser record
    account_user_repo.update_status(
        target_user_id, account.id, AccountUserStatus.deactivated
    )

    # 6. Remove all role assignments
    role_repo.remove_all_roles_for_user_on_resource(
        target_user_id, ResourceType.ACCOUNT, account.id
    )

    # 7. Send notification email (TODO)


# ============================================================================
# INVITATION FLOW - SYNC
# ============================================================================


def get_invitation_details(
    session: Session,
    token: str,
) -> tuple[db.UserInvitation, str, str | None, str] | None:
    """
    Get invitation details by token (public endpoint, no auth).

    Steps:
    1. Get invitation by token
    2. Check if expired and mark if so
    3. Get account name and display name
    4. Get inviter's email/name
    5. Return invitation, account name, account display name, and inviter info

    Args:
        session: Database session
        token: Invitation token

    Returns:
        Tuple of (invitation, account_name, account_display_name, inviter_email) or None if not found
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
    account_display_name = account.display_name if account else None

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

    return invitation, account_name, account_display_name, inviter_email


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
    3. Check Cognito user status
    4. Resend email with appropriate template
    5. Return invitation

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

    # 3. Extend invitation expiration (7 days from now)
    new_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    invitation_repo.update_expiration(invitation.id, new_expires_at)
    invitation.expires_at = new_expires_at  # Update in-memory object
    logger.info(
        f"Extended invitation expiration to {new_expires_at} for {invitation.email}"
    )

    # 4. Get account details
    account_repo = AccountRepository(session)
    account = account_repo.get_account_by_id(invitation.account_id)
    if not account:
        raise ValueError("Account not found")

    # 4. Check Cognito user status
    user_name = invitation.email.split("@")[0].replace(".", " ").title()
    aws_region = os.environ.get("AWS_REGION", "us-east-1")
    user_pool_id = os.environ.get("AWS_ADMIN_CONSOLE_USER_POOL_ID")

    user_exists = False
    user_status = None
    if user_pool_id:
        user_exists, user_status = get_cognito_user_status(
            invitation.email, user_pool_id, aws_region
        )

    # 5. Resend email with appropriate template
    try:
        # Get inviter details
        account_user_repo = AccountUserRepository(session)
        inviter = account_user_repo.get_by_user_and_account(
            invitation.invited_by, invitation.account_id
        )
        inviter_name = inviter.name if inviter else "A team member"
        account_display_name = account.display_name or account.name

        # Base template model
        template_model = {
            "name": user_name,
            "inviter_name": inviter_name,
            "account_name": account_display_name,
            "role": invitation.account_role,
            "product_name": "Palona AI",
            "sender_name": "Support Team",
        }

        # Construct base URL
        base_url = (
            "https://console.palona.ai"
            if os.getenv("RUNTIME_ENV", "prd") == "prd"
            else f"https://{os.getenv('RUNTIME_ENV', 'lat')}-console.palona.ai"
        )

        # Determine which email template to use based on user status
        password = None
        user_recreated = False

        if not user_exists:
            # User doesn't exist - recreate them
            if not user_pool_id:
                raise ValueError(
                    "AWS_ADMIN_CONSOLE_USER_POOL_ID is not configured; "
                    "cannot recreate Cognito user during invitation resend"
                )

            password = generate_password()
            try:
                cognito_client = boto3.client("cognito-idp", region_name=aws_region)
                cognito_client.admin_create_user(
                    UserPoolId=user_pool_id,
                    Username=invitation.email,
                    TemporaryPassword=password,
                    MessageAction="SUPPRESS",
                    UserAttributes=[
                        {"Name": "email", "Value": invitation.email},
                        {"Name": "email_verified", "Value": "true"},
                        {"Name": "name", "Value": user_name},
                    ],
                )
                user_recreated = True
                logger.info(f"Recreated Cognito user for resend: {invitation.email}")
            except ClientError as e:
                logger.error(f"Failed to recreate Cognito user: {e}")
                raise ValueError(f"Failed to recreate Cognito user: {e}") from e

            template_id = TEAM_INVITATION_NEW_USER_TEMPLATE_ID
            template_model["email"] = invitation.email
            template_model["login_url"] = f"{base_url}/signin?email={invitation.email}"
        elif user_exists and user_status == "FORCE_CHANGE_PASSWORD":
            # User created but never logged in - reset their temporary password
            # This handles the case where the original temp password expired (7 days)
            if not user_pool_id:
                raise ValueError(
                    "AWS_ADMIN_CONSOLE_USER_POOL_ID is not configured; "
                    "cannot reset temporary password during invitation resend"
                )

            password = generate_password()
            try:
                cognito_client = boto3.client("cognito-idp", region_name=aws_region)
                cognito_client.admin_set_user_password(
                    UserPoolId=user_pool_id,
                    Username=invitation.email,
                    Password=password,
                    Permanent=False,  # This makes it a temporary password
                )
                user_recreated = True
                logger.info(
                    f"Reset temporary password for {invitation.email} (original password may have expired)"
                )
            except ClientError as e:
                logger.error(f"Failed to reset temporary password: {e}")
                raise ValueError(f"Failed to reset temporary password: {e}") from e

            # Send NEW USER template with embedded password (not pending user template)
            template_id = TEAM_INVITATION_NEW_USER_TEMPLATE_ID
            template_model["email"] = invitation.email
            template_model["login_url"] = f"{base_url}/signin?email={invitation.email}"
        else:
            # Existing confirmed user
            template_id = TEAM_INVITATION_EXISTING_USER_TEMPLATE_ID
            template_model["login_url"] = f"{base_url}/signin"
            logger.info(
                f"Resending existing user invitation to {invitation.email} (already confirmed)"
            )

        # Generate JWT token that includes temporary password for recreated users
        jwt_token = generate_invitation_jwt(
            invitation_token=invitation.invitation_token,
            email=invitation.email,
            temporary_password=password if user_recreated else None,
            expires_at=invitation.expires_at,
        )
        template_model["invitation_url"] = (
            f"{base_url}/accept-invitation?token={jwt_token}"
        )

        email_service.send_email_with_template(
            to_email=invitation.email,
            template_id=template_id,
            template_model=template_model,
            bcc_emails=["notifications@palona.ai"],
        )
        logger.info(
            f"Invitation email resent to {invitation.email} for account {account.name}"
        )
    except Exception as e:
        logger.error(f"Failed to resend invitation email to {invitation.email}: {e}")
        raise ValueError(
            f"Failed to send invitation email to {invitation.email}"
        ) from e

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


def list_user_accounts_by_email(
    context: UserContext,
    session: Session,
    user_email: str,
) -> list[tuple[UUID, db.Account, str | None, datetime]]:
    """
    List all accounts a user has access to by their email address.

    This is an admin-only function that allows looking up account memberships
    by user email instead of requiring authentication context.

    Steps:
    1. Verify caller is an admin
    2. Verify AWS Cognito user pool is configured
    3. Get user_id from Cognito by email
    4. Get all account memberships for user
    5. For each membership, get account details and role
    6. Return list of (user_id, account, role, last_accessed) tuples

    Args:
        context: User context for authorization
        session: Database session
        user_email: Email address of the user to look up

    Returns:
        List of tuples: (user_id, account, primary_role, last_accessed)

    Raises:
        ValueError: If user is not an admin, AWS Cognito not configured,
                    or user not found in Cognito
    """
    # 1. Verify caller is an admin to prevent cross-tenant info leak
    if context.role != UserRole.Admin:
        raise ValueError("Only admin users can look up accounts by email")

    # 2. Verify AWS Cognito user pool is configured
    if not AWS_ADMIN_CONSOLE_USER_POOL_ID:
        raise ValueError(
            "AWS_ADMIN_CONSOLE_USER_POOL_ID is not configured; "
            "cannot retrieve user from Cognito"
        )

    # 3. Get user_id from Cognito by email
    cognito_client = boto3.client("cognito-idp", region_name=AWS_REGION)

    try:
        user_response = cognito_client.admin_get_user(
            UserPoolId=AWS_ADMIN_CONSOLE_USER_POOL_ID, Username=user_email
        )

        # Extract user_sub (user_id) from attributes
        user_sub = None
        for attr in user_response["UserAttributes"]:
            if attr["Name"] == "sub":
                user_sub = attr["Value"]
                break

        if not user_sub:
            raise ValueError(f"User sub not found for email: {user_email}")

        user_id = UUID(user_sub)

    except ClientError as e:
        if e.response["Error"]["Code"] == "UserNotFoundException":
            raise ValueError(f"User not found with email: {user_email}") from e
        else:
            logger.error(f"Error retrieving user from Cognito: {e}")
            raise ValueError(f"Failed to retrieve user: {e}") from e

    # 4. Get all account memberships for user
    account_user_repo = AccountUserRepository(session)
    account_memberships = account_user_repo.get_accounts_for_user(user_id)

    # 5. For each membership, get account details and role
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

        result.append((user_id, account, primary_role, last_accessed))

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


def get_pending_invitations_for_user(
    session: Session,
    email: str,
) -> list[
    tuple[
        db.UserInvitation,
        str,  # account_name
        str | None,  # account_display_name
        str,  # inviter_name or email
    ]
]:
    """
    Get all pending invitations for a user by email.

    Args:
        session: Database session
        email: User's email address

    Returns:
        List of tuples containing (invitation, account_name, account_display_name, inviter_name)
    """
    # Initialize repositories
    invitation_repo = UserInvitationRepository(session, auto_commit=False)
    account_repo = AccountRepository(session, auto_commit=False)
    account_user_repo = AccountUserRepository(session, auto_commit=False)

    # Get all pending invitations for this email using repository
    invitations = invitation_repo.get_pending_for_email(email)

    results = []
    for invitation in invitations:
        # Get account using repository
        account = account_repo.get_account_by_id(invitation.account_id)
        if not account:
            continue

        # Get inviter info from AccountUser table using repository
        inviter_account_user = account_user_repo.get_by_user_id(invitation.invited_by)

        # Prefer name, fallback to email, then "Unknown"
        inviter_name = "Unknown"
        if inviter_account_user:
            if inviter_account_user.name:
                inviter_name = inviter_account_user.name
            elif inviter_account_user.email:
                inviter_name = inviter_account_user.email

        results.append(
            (
                invitation,
                account.name,
                account.display_name,
                inviter_name,
            )
        )

    return results


def accept_multiple_invitations(
    session: Session,
    context: UserContext,
    invitation_tokens: list[str],
) -> list[tuple[str, bool, db.Account | None, str | None, str | None]]:
    """
    Accept multiple invitations at once.

    Args:
        session: Database session
        context: User context
        invitation_tokens: List of invitation tokens to accept

    Returns:
        List of tuples: (token, success, account, role, error_message)
    """
    results = []

    for token in invitation_tokens:
        try:
            # Try to accept the invitation
            account, role = accept_invitation(
                session=session,
                context=context,
                params=AcceptInvitationParams(invitation_token=token),
            )
            results.append((token, True, account, role, None))
        except ValueError as e:
            # Invitation failed - record error
            results.append((token, False, None, None, str(e)))
        except Exception as e:
            # Unexpected error
            logger.error(f"Error accepting invitation {token}: {e}", exc_info=True)
            results.append((token, False, None, None, "An unexpected error occurred"))

    return results


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
