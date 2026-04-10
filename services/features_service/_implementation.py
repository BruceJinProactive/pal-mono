"""
Features service implementation for managing feature flags.
"""

import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

import db
from db.tables.types import IdentifierType
from utils.log import logger
from utils.otel import traced

# Simple TTL cache for feature flag checks
# Key: (feature, identifier_type, identifier) -> Value: (result, timestamp)
_CacheKey = tuple[str, IdentifierType, str]
_feature_cache: dict[_CacheKey, tuple[bool, float]] = {}
_FEATURE_CACHE_TTL = 300  # 5 minutes
_MAX_FEATURE_CACHE_ENTRIES = 10_000


def _get_cache_key(
    feature: str, identifier_type: IdentifierType, identifier: str
) -> _CacheKey:
    return (feature, identifier_type, identifier)


def _get_cached(key: _CacheKey) -> Optional[bool]:
    """Get cached result if not expired."""
    if key in _feature_cache:
        result, timestamp = _feature_cache[key]
        if time.time() - timestamp < _FEATURE_CACHE_TTL:
            return result
        del _feature_cache[key]
    return None


def _set_cached(key: _CacheKey, result: bool) -> None:
    """Cache result with current timestamp."""
    if len(_feature_cache) >= _MAX_FEATURE_CACHE_ENTRIES:
        # Drop oldest entry to cap memory growth
        oldest_key = min(_feature_cache.items(), key=lambda item: item[1][1])[0]
        _feature_cache.pop(oldest_key, None)
    _feature_cache[key] = (result, time.time())


def invalidate_feature_cache(
    feature: str, identifier_type: IdentifierType, identifier: str
) -> None:
    """Invalidate cached result for a specific feature/identifier."""
    key = _get_cache_key(feature, identifier_type, identifier)
    _feature_cache.pop(key, None)


@traced("features_service:check_feature_enabled()")
async def check_feature_enabled(
    session: AsyncSession,
    feature: str,
    identifier_type: IdentifierType,
    identifier: str,
) -> bool:
    """
    Check if a feature is enabled for a specific identifier.

    Results are cached for 5 minutes to reduce DB load.

    Args:
        session: The async database session
        feature: The feature name to check
        identifier_type: The type of identifier (agent, account, project, user)
        identifier: The identifier value (UUID or string ID)

    Returns:
        bool: True if the feature is enabled, False otherwise
    """
    cache_key = _get_cache_key(feature, identifier_type, identifier)

    cached = _get_cached(cache_key)
    if cached is not None:
        return cached

    try:
        feature_repo = db.FeatureRepositoryAsync(session)
        result = await feature_repo.check_enablement(
            feature=feature,
            identifier_type=identifier_type,
            identifier=identifier,
        )
        _set_cached(cache_key, result)
        return result
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
    # Invalidate cache before updating
    invalidate_feature_cache(feature, identifier_type, identifier)

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
