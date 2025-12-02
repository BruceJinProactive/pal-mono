"""
Feature flags for RBAC migration.

Provides simple environment-based feature flags for controlling
RBAC behavior during the migration period.
"""


def is_rbac_enabled() -> bool:
    """
    Check if RBAC is enabled.

    Returns:
        Always returns True as RBAC is now fully enabled.
    """
    return True
