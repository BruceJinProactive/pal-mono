"""
RBAC Authorization (v1 - Account Level)

This module handles permission checking for the RBAC system.
In v1, permissions are loaded from config. In v2, they'll come from database.
"""

from typing import Optional, Set
from uuid import UUID

from sqlalchemy.orm import Session

from db.repositories.account_user_repository import AccountUserRepository
from db.repositories.resource_role_assignment_repository import (
    ResourceRoleAssignmentRepository,
)
from services.auth_service.config import ROLE_PERMISSIONS
from utils.log import logger


def get_user_role_on_account(
    user_id: UUID, account_id: UUID, session: Session
) -> Optional[str]:
    """
    Get user's role on account (V1 - account-level only).

    Returns the first role found for the user on the account resource.
    In v1, we assume one role per user per account for simplicity.

    Args:
        user_id: User's ID
        account_id: Account ID
        session: Database session

    Returns:
        Role string (e.g., 'owner', 'manager', 'viewer') or None if no role
    """
    try:
        # First verify user is a member of the account
        account_user_repo = AccountUserRepository(session, auto_commit=False)
        if not account_user_repo.is_member(user_id, account_id):
            logger.debug(f"User {user_id} is not a member of account {account_id}")
            return None

        # Get role from resource_role_assignments
        role_repo = ResourceRoleAssignmentRepository(session, auto_commit=False)
        roles = role_repo.get_roles_for_resource(
            user_id=user_id, resource_type="account", resource_id=account_id
        )

        if not roles:
            logger.debug(f"User {user_id} has no role assigned on account {account_id}")
            return None

        # V1: Return first role (assumes single role per user per account)
        # V2 will support multiple roles per resource
        return roles[0]

    except Exception as e:
        logger.error(f"Error getting user role on account: {e}")
        return None


def get_role_permissions(role: str) -> Set[str]:
    """
    Get permissions for a role (v1: from config).

    Args:
        role: Role string (e.g., 'owner', 'manager', 'viewer')

    Returns:
        Set of permission names (e.g., {'project.create', 'agent.read'})
    """
    # Special case: Owner has all permissions
    if role == "owner":
        return {"*"}

    return ROLE_PERMISSIONS.get(role, set())


def check_permission(
    user_id: UUID, account_id: UUID, permission_name: str, session: Session
) -> bool:
    """
    Check if user has permission on account (V1 - account-level only).

    Args:
        user_id: User ID
        account_id: Account ID
        permission_name: Permission to check (e.g., "project.create")
        session: Database session

    Returns:
        True if user has permission, False otherwise
    """
    try:
        # Get user's role on account
        role = get_user_role_on_account(user_id, account_id, session)

        if not role:
            logger.debug(
                f"Permission denied: User {user_id} has no role on account {account_id}"
            )
            return False

        # Get permissions for role
        permissions = get_role_permissions(role)

        # Check permission (wildcard * means all permissions)
        has_permission = "*" in permissions or permission_name in permissions

        if not has_permission:
            logger.debug(
                f"Permission denied: User {user_id} with role {role} lacks {permission_name}"
            )

        return has_permission

    except Exception as e:
        logger.error(f"Error checking permission: {e}")
        return False
