"""
RBAC Permission Configuration (v1)

This file defines the permission model for the Palona platform.
In v1, permissions are statically defined here. In v2, these will
migrate to database tables for dynamic management.
"""

from typing import Dict, Optional, Set

# =============================================================================
# ROLE PERMISSIONS
# =============================================================================

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    # Owner: Full access (wildcard)
    "owner": {"*"},
    # Manager: Can manage projects/agents, approve plans, export data
    # Cannot: modify billing, manage team
    "manager": {
        "account.read",
        "project.create",
        "project.read",
        "project.write",
        "project.delete",
        "agent.create",
        "agent.read",
        "agent.write",
        "agent.delete",
        "plan.approve",
        "data.export",
    },
    # Viewer: Read-only access + data export
    # Cannot: create/modify anything
    "viewer": {
        "account.read",
        "project.read",
        "agent.read",
        "data.export",
    },
}

# =============================================================================
# RESOURCE HIERARCHY
# =============================================================================
# Defines parent-child relationships for hierarchical permission checking

RESOURCE_HIERARCHY: Dict[str, Optional[str]] = {
    "checklists": "projects",  # Checklist belongs to project
    "projects": "accounts",  # Project belongs to account
    "agents": "accounts",  # Agent belongs to account
    "accounts": None,  # Account is top-level (no parent)
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
        "resource_type": "plan",
    },
    # Data permissions
    "data.export": {
        "display_name": "Export Data",
        "description": "Export data and reports",
        "resource_type": "data",
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
