"""
Features service implementation for managing feature flags.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

import db
from db.tables.types import IdentifierType
from utils.dd import traced
from utils.log import logger


@traced("features_service:check_feature_enabled()")
async def check_feature_enabled(
    session: AsyncSession,
    feature: str,
    identifier_type: IdentifierType,
    identifier: str,
) -> bool:
    """
    Check if a feature is enabled for a specific identifier.

    Args:
        session: The async database session
        feature: The feature name to check
        identifier_type: The type of identifier (agent, account, project, user)
        identifier: The identifier value (UUID or string ID)

    Returns:
        bool: True if the feature is enabled, False otherwise
    """
    try:
        feature_repo = db.FeatureRepositoryAsync(session)
        return await feature_repo.check_enablement(
            feature=feature,
            identifier_type=identifier_type,
            identifier=identifier,
        )
    except Exception as e:
        logger.error(
            f"Error checking feature {feature} for {identifier_type}/{identifier}: {e}"
        )
        # Default to disabled on error for safety
        return False


@traced("features_service:upsert_feature()")
async def upsert_feature(
    session: AsyncSession,
    feature: str,
    identifier_type: IdentifierType,
    identifier: str,
    enabled: bool,
) -> Optional[db.Feature]:
    """
    Create or update a feature flag entry.

    Args:
        session: The async database session
        feature: The feature name
        identifier_type: The type of identifier (agent, account, project, user)
        identifier: The identifier value (UUID or string ID)
        enabled: Whether the feature should be enabled

    Returns:
        Feature: The created or updated feature entry, or None if operation failed
    """
    try:
        feature_repo = db.FeatureRepositoryAsync(session)
        return await feature_repo.upsert(
            feature=feature,
            identifier_type=identifier_type,
            identifier=identifier,
            enabled=enabled,
        )
    except Exception as e:
        logger.error(
            f"Error upserting feature {feature} for {identifier_type}/{identifier}: {e}"
        )
        return None
