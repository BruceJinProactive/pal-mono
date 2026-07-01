"""
RBAC Auth Service

Provides Role-Based Access Control (RBAC) functionality for the Palona platform.
In v1, permissions are config-based for simplicity. In v2, they'll migrate to database.
"""

from services.auth_service.authorization import (
    VALID_RESOURCE_TYPES,
    check_permission,
    get_merged_permissions,
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
    require_account_membership,
    require_account_permission,
    require_agent_permission,
    require_campaign_permission,
    require_execution_permission,
    require_feedback_permission,
    require_history_permission,
    require_knowledge_permission,
    require_permission,
    require_project_permission,
    require_routine_permission,
    require_submission_permission,
    require_subscription_permission,
    resolve_project_scope_or_raise,
)
from services.auth_service.resolution import (
    get_parent_resource,
    resolve_account_identifier,
    resolve_resource_identifier,
)
from services.auth_service.scope import (
    ProjectScopeForbiddenError,
    authorize_requested_project_ids,
    get_accessible_project_ids,
    get_account_project_ids,
    resolve_project_scope,
)

__all__ = [
    # Authorization functions
    "get_user_role_on_account",
    "get_role_permissions",
    "get_merged_permissions",
    "check_permission",
    "parse_resource_id",
    # Resolution functions
    "resolve_account_identifier",
    "resolve_resource_identifier",
    "get_parent_resource",
    # Store scope helpers
    "ProjectScopeForbiddenError",
    "get_account_project_ids",
    "get_accessible_project_ids",
    "authorize_requested_project_ids",
    "resolve_project_scope",
    # FastAPI dependencies
    "PermissionChecker",
    "resolve_project_scope_or_raise",
    "require_permission",
    # FastAPI dependency factories (recommended for most use cases)
    "require_account_membership",
    "require_account_permission",
    "require_project_permission",
    "require_agent_permission",
    "require_history_permission",
    "require_feedback_permission",
    "require_campaign_permission",
    "require_knowledge_permission",
    "require_subscription_permission",
    # Routine/Execution/Submission permission factories
    "require_routine_permission",
    "require_execution_permission",
    "require_submission_permission",
    # Config and constants
    "ROLE_PERMISSIONS",
    "PERMISSION_REGISTRY",
    "RESOURCE_HIERARCHY",
    "VALID_RESOURCE_TYPES",
    "get_all_permissions",
    "get_permissions_for_resource",
    "get_permission_display_name",
]
