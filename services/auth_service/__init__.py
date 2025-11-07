"""
RBAC Auth Service

Provides Role-Based Access Control (RBAC) functionality for the Palona platform.
In v1, permissions are config-based for simplicity. In v2, they'll migrate to database.
"""

from services.auth_service.authorization import (
    VALID_RESOURCE_TYPES,
    check_permission,
    get_role_permissions,
    get_user_role_on_account,
    parse_resource_id,
)
from services.auth_service.config import (
    PERMISSION_REGISTRY,
    RESOURCE_HIERARCHY,
    ROLE_PERMISSIONS,
    get_all_permissions,
    get_permission_display_name,
    get_permissions_for_resource,
)
from services.auth_service.dependencies import (
    PermissionChecker,
    require_account_permission,
    require_agent_permission,
    require_checklist_permission,
    require_permission,
    require_project_permission,
    require_resource_permission,
)
from services.auth_service.resolution import (
    get_parent_resource,
    resolve_account_identifier,
    resolve_resource_identifier,
)

__all__ = [
    # Authorization functions
    "get_user_role_on_account",
    "get_role_permissions",
    "check_permission",
    "parse_resource_id",
    # Resolution functions
    "resolve_account_identifier",
    "resolve_resource_identifier",
    "get_parent_resource",
    # FastAPI dependencies
    "PermissionChecker",
    "require_permission",
    # FastAPI dependency factories (recommended for most use cases)
    "require_account_permission",
    "require_project_permission",
    "require_checklist_permission",
    "require_agent_permission",
    "require_resource_permission",
    # Config and constants
    "ROLE_PERMISSIONS",
    "PERMISSION_REGISTRY",
    "RESOURCE_HIERARCHY",
    "VALID_RESOURCE_TYPES",
    "get_all_permissions",
    "get_permissions_for_resource",
    "get_permission_display_name",
]
