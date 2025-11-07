"""
RBAC Auth Service

Provides Role-Based Access Control (RBAC) functionality for the Palona platform.
In v1, permissions are config-based for simplicity. In v2, they'll migrate to database.
"""

from services.auth_service.authorization import (
    check_permission,
    get_role_permissions,
    get_user_role_on_account,
)
from services.auth_service.config import (
    PERMISSION_REGISTRY,
    ROLE_PERMISSIONS,
    get_all_permissions,
    get_permission_display_name,
    get_permissions_for_resource,
)
from services.auth_service.dependencies import PermissionChecker, require_permission

__all__ = [
    # Authorization functions
    "get_user_role_on_account",
    "get_role_permissions",
    "check_permission",
    # FastAPI dependencies
    "PermissionChecker",
    "require_permission",
    # Config
    "ROLE_PERMISSIONS",
    "PERMISSION_REGISTRY",
    "get_all_permissions",
    "get_permissions_for_resource",
    "get_permission_display_name",
]
