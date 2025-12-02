"""
Feature flags for RBAC migration.

Provides simple environment-based feature flags for controlling
RBAC behavior during the migration period.
"""

import os

from utils.log import logger


def is_rbac_enabled() -> bool:
    """
    Check if RBAC is enabled via environment variable.

    When enabled, endpoints use the RBAC permission system.
    When disabled (default), endpoints fall back to legacy
    account membership checks.

    Returns:
        True if USE_RBAC environment variable is set to "true",
        False otherwise.
    """
    enabled = os.environ.get("USE_RBAC", "false").lower() == "true"
    if enabled:
        logger.debug("RBAC is enabled")
    return enabled
