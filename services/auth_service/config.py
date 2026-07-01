"""
RBAC Permission Configuration (v1)

This file defines the permission model for the Palona platform.
In v1, permissions are statically defined here. In v2, these will
migrate to database tables for dynamic management.
"""

from typing import Dict, Optional, Set

ACCOUNT_ADMIN_ROLE = "account_admin"
STORE_OWNER_ROLE = "store_owner"
STORE_MEMBER_ROLE = "store_member"

LEGACY_OWNER_ROLE = "owner"
LEGACY_MANAGER_ROLE = "manager"
LEGACY_VIEWER_ROLE = "viewer"
LEGACY_STAFF_ROLE = "staff"

ACCOUNT_ADMIN_ROLE_ALIASES = frozenset({ACCOUNT_ADMIN_ROLE, LEGACY_OWNER_ROLE})

# =============================================================================
# ROLE PERMISSIONS
# =============================================================================

ACCOUNT_ADMIN_PERMISSIONS: Set[str] = {
    "account.read",
    "account.status.read",
    "account.write",
    "account.billing.read",
    "account.billing.write",
    "account.team_manage",
    "project.create",
    "project.read",
    "project.write",
    "project.delete",
    "brand.read",
    "brand.write",
    "team.read",
    "team.manage",
    "conversation.read",
    "history.read",
    "feedback.read",
    "feedback.write",
    "agent.read",
    "billing.read",
    "billing.write",
    "docs.read",
    "catering.read",
    "catering.write",
    "operation.read",
    # Temporary compatibility for Operations routes that still check routine /
    # execution / submission permissions instead of operation.read.
    "routine.read",
    "routine.write",
    "execution.read.today",
    "execution.read.history",
    "submission.create",
    "submission.write",
    "submission.review",
    "plan.approve",
    "data.export",
}

STORE_OWNER_PERMISSIONS: Set[str] = {
    "account.read",
    "account.status.read",
    "project.read",
    "project.write",
    "team.manage",
    "conversation.read",
    "agent.read",
    "docs.read",
    "catering.read",
    "catering.write",
    "operation.read",
    # Temporary compatibility for Operations routes that still check routine /
    # execution / submission permissions instead of operation.read.
    "routine.read",
    "execution.read.today",
    "execution.read.history",
    "submission.create",
    "submission.write",
}

STORE_MEMBER_PERMISSIONS: Set[str] = {
    "account.read",
    "account.status.read",
    "project.read",
    "conversation.read",
    "agent.read",
    "docs.read",
    "catering.read",
    "operation.read",
    # Temporary compatibility for Operations routes that still check routine /
    # execution / submission permissions instead of operation.read.
    "routine.read",
    "execution.read.today",
    "execution.read.history",
    "submission.create",
    "submission.write",
}

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    # Canonical customer roles
    ACCOUNT_ADMIN_ROLE: set(ACCOUNT_ADMIN_PERMISSIONS),
    STORE_OWNER_ROLE: set(STORE_OWNER_PERMISSIONS),
    STORE_MEMBER_ROLE: set(STORE_MEMBER_PERMISSIONS),
    # Temporary migration aliases. Do not create new assignments with these keys.
    LEGACY_OWNER_ROLE: set(ACCOUNT_ADMIN_PERMISSIONS),
    LEGACY_MANAGER_ROLE: set(STORE_MEMBER_PERMISSIONS),
    LEGACY_VIEWER_ROLE: set(STORE_MEMBER_PERMISSIONS),
    # Staff is intentionally fail-closed for customer-console RBAC.
    LEGACY_STAFF_ROLE: set(),
}

# =============================================================================
# RESOURCE HIERARCHY
# =============================================================================
# Defines parent-child relationships for hierarchical permission checking.
#
# NOTE: This is METADATA ONLY for documentation and future UI purposes.
# The actual hierarchy traversal logic is implemented in resolution.py's
# get_parent_resource() function, which handles the database lookups needed
# to resolve parent resources (e.g., submission → execution → routine → project).
#
# When adding new resources:
# 1. Add entry here for documentation
# 2. Implement actual resolution in resolution.py:get_parent_resource()
# 3. Add to VALID_RESOURCE_TYPES in authorization.py

RESOURCE_HIERARCHY: Dict[str, Optional[str]] = {
    # Core resources
    "accounts": None,  # Account is top-level (no parent)
    "projects": "accounts",  # Project belongs to account
    "agents": "accounts",  # Agent belongs to account
    # Routine workflow resources (hierarchy: submission → execution → routine → project)
    "routines": "projects",  # Routine belongs to project
    "executions": "routines",  # Execution belongs to routine
    "submissions": "executions",  # Submission belongs to execution
    # Account-level resources
    "histories": "accounts",  # History/changelog belongs to account
    "feedbacks": "accounts",  # Feedback belongs to account (via message → conversation)
    "campaigns": "accounts",  # Campaign belongs to account
    "knowledges": "accounts",  # Knowledge belongs to account
    "subscriptions": "accounts",  # Subscription belongs to account
    "conversations": "projects",  # Conversation belongs to a store/project
    "catering_requests": "projects",  # Catering request belongs to a store/project
    "operations": "projects",  # Operations views are store/project scoped
    "brands": "accounts",  # Brand settings belong to the account
    "teams": "accounts",  # Team management belongs to the account
    "docs": "accounts",  # Customer docs are account scoped
    # Standalone resources (no hierarchy)
    "plans": None,  # Plans are top-level for now
    "data": None,  # Data resources are top-level for now
}

# =============================================================================
# PERMISSION REGISTRY
# =============================================================================
# Metadata for all permissions (useful for documentation, future UI)

PERMISSION_REGISTRY: Dict[str, Dict[str, str]] = {
    # Account permissions
    "account.read": {
        "display_name": "View Account",
        "description": "View account settings and information",
        "resource_type": "accounts",
    },
    "account.status.read": {
        "display_name": "View Account Status",
        "description": "View basic account status (e.g., terms acceptance)",
        "resource_type": "accounts",
    },
    "account.write": {
        "display_name": "Modify Account",
        "description": "Modify account settings",
        "resource_type": "accounts",
    },
    "account.billing.read": {
        "display_name": "View Billing",
        "description": "View billing information",
        "resource_type": "accounts",
    },
    "account.billing.write": {
        "display_name": "Modify Billing",
        "description": "Modify billing settings",
        "resource_type": "accounts",
    },
    "account.team_manage": {
        "display_name": "Manage Team",
        "description": "Invite and remove team members",
        "resource_type": "accounts",
    },
    # Brand permissions
    "brand.read": {
        "display_name": "View Brand",
        "description": "View brand settings",
        "resource_type": "brands",
    },
    "brand.write": {
        "display_name": "Modify Brand",
        "description": "Modify brand settings",
        "resource_type": "brands",
    },
    # Team permissions
    "team.read": {
        "display_name": "View Team",
        "description": "View team members",
        "resource_type": "teams",
    },
    "team.manage": {
        "display_name": "Manage Team",
        "description": "Invite and manage team members",
        "resource_type": "teams",
    },
    # Conversation and feedback permissions
    "conversation.read": {
        "display_name": "View Conversations",
        "description": "View conversations",
        "resource_type": "conversations",
    },
    "history.read": {
        "display_name": "View History",
        "description": "View conversation history",
        "resource_type": "histories",
    },
    "feedback.read": {
        "display_name": "View Feedback",
        "description": "View feedback",
        "resource_type": "feedbacks",
    },
    "feedback.write": {
        "display_name": "Modify Feedback",
        "description": "Create and modify feedback",
        "resource_type": "feedbacks",
    },
    # Billing permissions
    "billing.read": {
        "display_name": "View Billing",
        "description": "View billing information",
        "resource_type": "subscriptions",
    },
    "billing.write": {
        "display_name": "Modify Billing",
        "description": "Modify billing settings",
        "resource_type": "subscriptions",
    },
    # Docs permissions
    "docs.read": {
        "display_name": "View Docs",
        "description": "View customer documentation",
        "resource_type": "docs",
    },
    # Catering permissions
    "catering.read": {
        "display_name": "View Catering Requests",
        "description": "View catering requests",
        "resource_type": "catering_requests",
    },
    "catering.write": {
        "display_name": "Modify Catering Requests",
        "description": "Modify catering requests",
        "resource_type": "catering_requests",
    },
    # Operations permissions
    "operation.read": {
        "display_name": "View Operations",
        "description": "View Operations and Vision data",
        "resource_type": "operations",
    },
    # Project permissions
    "project.create": {
        "display_name": "Create Projects",
        "description": "Create new projects",
        "resource_type": "projects",
    },
    "project.read": {
        "display_name": "View Projects",
        "description": "View project configurations",
        "resource_type": "projects",
    },
    "project.write": {
        "display_name": "Modify Projects",
        "description": "Modify project settings",
        "resource_type": "projects",
    },
    "project.delete": {
        "display_name": "Delete Projects",
        "description": "Delete projects",
        "resource_type": "projects",
    },
    # Agent permissions
    "agent.create": {
        "display_name": "Create Agents",
        "description": "Create new agents",
        "resource_type": "agents",
    },
    "agent.read": {
        "display_name": "View Agents",
        "description": "View agent configurations",
        "resource_type": "agents",
    },
    "agent.write": {
        "display_name": "Modify Agents",
        "description": "Modify agent settings",
        "resource_type": "agents",
    },
    "agent.delete": {
        "display_name": "Delete Agents",
        "description": "Delete agents",
        "resource_type": "agents",
    },
    # Plan permissions
    "plan.approve": {
        "display_name": "Approve Plans",
        "description": "Approve automated plans",
        "resource_type": "plans",
    },
    # Data permissions
    "data.export": {
        "display_name": "Export Data",
        "description": "Export data and reports",
        "resource_type": "data",
    },
    # Routine permissions
    "routine.read": {
        "display_name": "View Routines",
        "description": "View routine templates and items",
        "resource_type": "routines",
    },
    "routine.write": {
        "display_name": "Modify Routines",
        "description": "Create and modify routine templates",
        "resource_type": "routines",
    },
    # Execution permissions
    "execution.read.today": {
        "display_name": "View Today's Executions",
        "description": "View execution instances scheduled for today only",
        "resource_type": "executions",
    },
    "execution.read.history": {
        "display_name": "View Execution History",
        "description": "View historical execution instances",
        "resource_type": "executions",
    },
    # Submission permissions
    "submission.create": {
        "display_name": "Start Submissions",
        "description": "Start new routine submissions",
        "resource_type": "submissions",
    },
    "submission.write": {
        "display_name": "Modify Submissions",
        "description": "Modify submissions (add responses, update status)",
        "resource_type": "submissions",
    },
    "submission.review": {
        "display_name": "Review Submissions",
        "description": "Approve or reject submissions",
        "resource_type": "submissions",
    },
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_all_permissions() -> Set[str]:
    """Get all permission names."""
    return set(PERMISSION_REGISTRY.keys())


def get_permissions_for_resource(resource_type: str) -> Set[str]:
    """Get all permission names for a specific resource type."""
    return {
        name
        for name, meta in PERMISSION_REGISTRY.items()
        if meta["resource_type"] == resource_type
    }


def get_permission_display_name(permission: str) -> str:
    """Get display name for a permission."""
    return PERMISSION_REGISTRY.get(permission, {}).get("display_name", permission)
