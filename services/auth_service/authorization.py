"""
RBAC Authorization (v1 - Account Level)

This module handles permission checking for the RBAC system.
In v1, permissions are loaded from config. In v2, they'll come from database.
"""

from typing import TYPE_CHECKING, Optional, Set
from uuid import UUID

from sqlalchemy.orm import Session

from db.repositories.account_user_repository import AccountUserRepository
from db.repositories.resource_role_assignment_repository import (
    ResourceRoleAssignmentRepository,
    ResourceType,
)
from services.auth_service.config import ROLE_PERMISSIONS
from services.auth_service.resolution import (
    get_parent_resource,
    resolve_resource_identifier,
)
from utils.log import logger

if TYPE_CHECKING:
    pass

# Valid resource types for RBAC (v1)
VALID_RESOURCE_TYPES = {
    "accounts",
    "projects",
    "agents",
    "checklists",
    "plans",
    "data",
    "histories",
    "feedbacks",
    # Routine-related resources
    "routines",
    "executions",
    "submissions",
}


def parse_resource_id(resource_id: str) -> tuple[str, str]:
    """
    Parse resource_id in format "resource_type/identifier".

    Validates format and resource type, but does NOT validate identifier format.
    The identifier can be a name (for accounts) or UUID (for all resources).
    Resolution happens later in check_permission().

    Args:
        resource_id: Resource identifier (e.g., "accounts/palona", "checklists/uuid")

    Returns:
        Tuple of (resource_type, identifier_string)

    Raises:
        ValueError: If format is invalid or resource_type not whitelisted

    Examples:
        >>> parse_resource_id("accounts/palona")
        ("accounts", "palona")

        >>> parse_resource_id("checklists/123e4567-e89b-12d3-a456-426614174000")
        ("checklists", "123e4567-e89b-12d3-a456-426614174000")

        >>> parse_resource_id("invalid/format/too/many")
        ValueError: Invalid resource_id format
    """
    # Split by '/' and validate format
    parts = resource_id.split("/")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid resource_id format: {resource_id}. "
            f"Expected 'resource_type/identifier' (e.g., 'accounts/palona')"
        )

    resource_type, identifier = parts

    # Validate resource type is whitelisted
    if resource_type not in VALID_RESOURCE_TYPES:
        raise ValueError(
            f"Invalid resource_type: '{resource_type}'. "
            f"Must be one of {sorted(VALID_RESOURCE_TYPES)}"
        )

    # Validate identifier is not empty
    if not identifier or not identifier.strip():
        raise ValueError("Invalid resource_id: identifier cannot be empty")

    return resource_type, identifier


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
            user_id=user_id, resource_type=ResourceType.ACCOUNT, resource_id=account_id
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


def get_merged_permissions(roles: list[str]) -> Set[str]:
    """
    Get merged permissions from multiple roles.

    When a user has multiple roles, their effective permissions are the union
    of all permissions from each role.

    Args:
        roles: List of role strings (e.g., ['staff', 'manager'])

    Returns:
        Set of all permission names from all roles. If any role has wildcard (*),
        returns {'*'}.
    """
    if not roles:
        return set()

    merged: Set[str] = set()
    for role in roles:
        permissions = get_role_permissions(role)
        # If any role has wildcard, return immediately
        if "*" in permissions:
            return {"*"}
        merged.update(permissions)

    return merged


def check_permission(
    user_id: UUID,
    resource_id: str,
    permission_name: str,
    session: Session,
    check_hierarchy: bool = True,
    user_role: Optional[str] = None,
) -> bool:
    """
    Check if user has permission on resource with identifier resolution and hierarchical checking.

    Supports:
    - Name or UUID identifiers for accounts (e.g., "accounts/palona" or "accounts/uuid")
    - UUID identifiers for other resources
    - Hierarchical permission checking (checklist → project → account)
    - Admin bypass (when user_role="Admin", grants all permissions)

    Process:
    1. Check for admin bypass (if user_role provided)
    2. Parse resource_id into (resource_type, identifier)
    3. Resolve identifier to UUID using resolution layer
    4. Check direct permission on resource
    5. If not found AND check_hierarchy=True:
       - Get parent resource (e.g., checklist → project)
       - Recursively check parent permissions
    6. Return result

    Args:
        user_id: User ID
        resource_id: Resource identifier in format "resource_type/identifier"
                    (e.g., "accounts/palona", "checklists/uuid")
        permission_name: Permission to check (e.g., "project.create", "checklist.read")
        session: Database session
        check_hierarchy: Whether to check parent resources if permission not found (default True)
        user_role: Optional user role string for admin bypass (e.g., "Admin")

    Returns:
        True if user has permission, False otherwise

    Examples:
        >>> check_permission(user_id, "accounts/palona", "project.create", session)
        True

        >>> check_permission(user_id, "checklists/uuid", "checklist.read", session)
        True  # May be granted via checklist, project, or account role

        >>> check_permission(user_id, "any/resource", "any.permission", session, user_role="Admin")
        True  # Admin bypass
    """
    # Admin bypass - admins have all permissions
    if user_role == "Admin":
        logger.debug(f"Permission granted: User {user_id} is Admin (bypass)")
        return True

    try:
        # Parse and validate resource_id format
        resource_type, identifier = parse_resource_id(resource_id)

        # Resolve identifier to UUID (handles name → UUID for accounts)
        try:
            resolved_uuid = resolve_resource_identifier(
                resource_type, identifier, session
            )
        except ValueError as e:
            logger.debug(f"Resource resolution failed: {e}")
            return False

        # Check direct permission on this resource
        role_repo = ResourceRoleAssignmentRepository(session, auto_commit=False)
        # Convert plural resource_type (from API) to singular enum (for DB)
        resource_type_enum = ResourceType.from_plural(resource_type)
        roles = role_repo.get_roles_for_resource(
            user_id=user_id, resource_type=resource_type_enum, resource_id=resolved_uuid
        )

        if roles:
            # Merge permissions from all roles
            permissions = get_merged_permissions(roles)

            # Check permission (wildcard * means all permissions)
            if "*" in permissions or permission_name in permissions:
                logger.debug(
                    f"Permission granted: User {user_id} has {permission_name} "
                    f"via roles {roles} on {resource_id}"
                )
                return True

        # If no permission found on this resource, try hierarchical checking
        if check_hierarchy:
            parent = get_parent_resource(resource_type, resolved_uuid, session)
            if parent:
                parent_type, parent_id = parent
                parent_resource_id = f"{parent_type}/{parent_id}"
                logger.debug(
                    f"Checking parent resource {parent_resource_id} for permission {permission_name}"
                )
                return check_permission(
                    user_id=user_id,
                    resource_id=parent_resource_id,
                    permission_name=permission_name,
                    session=session,
                    check_hierarchy=True,  # Continue checking up the hierarchy
                    user_role=user_role,  # Pass through for consistency (already checked)
                )

        # No permission found
        logger.debug(
            f"Permission denied: User {user_id} lacks {permission_name} on {resource_id}"
            + (" (checked hierarchy)" if check_hierarchy else "")
        )
        return False

    except ValueError as e:
        # Invalid resource_id format
        logger.error(f"Invalid resource_id format: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking permission: {e}")
        return False
