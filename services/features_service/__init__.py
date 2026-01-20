"""
Features service for managing feature flags in the gatekeeper service.

This service provides functionality to check and upsert feature flags
for different identifier types (agent, account, project, user).
"""

from ._implementation import (
    check_feature_enabled,
    invalidate_feature_cache,
    upsert_feature,
)

__all__ = [
    "check_feature_enabled",
    "invalidate_feature_cache",
    "upsert_feature",
]
