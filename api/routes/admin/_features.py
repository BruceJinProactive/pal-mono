"""
Features endpoints implementation for managing feature flags.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.admin._utils import UserContext
from api.schemas.admin.features import (
    CheckFeatureRequest,
    CheckFeatureResponse,
    UpsertFeatureRequest,
    UpsertFeatureResponse,
)
from services import features_service
from utils.log import logger


async def check_feature(
    request: CheckFeatureRequest,
    context: UserContext,
    session: AsyncSession,
) -> CheckFeatureResponse:
    """
    Check if a feature is enabled for a specific identifier.

    Args:
        request: The check feature request
        context: User context for authorization
        session: Async database session

    Returns:
        CheckFeatureResponse with the feature status
    """
    try:
        is_enabled = await features_service.check_feature_enabled(
            session=session,
            feature=request.feature,
            identifier_type=request.identifier_type,
            identifier=request.identifier,
        )

        return CheckFeatureResponse(
            feature=request.feature,
            identifier_type=request.identifier_type,
            identifier=request.identifier,
            enabled=is_enabled,
        )
    except Exception as e:
        logger.error(f"Error checking feature: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check feature status",
            headers={"Content-Type": "application/json"},
        )


async def upsert_feature(
    request: UpsertFeatureRequest,
    context: UserContext,
    session: AsyncSession,
) -> UpsertFeatureResponse:
    """
    Create or update a feature flag.

    Args:
        request: The upsert feature request
        context: User context for authorization
        session: Async database session

    Returns:
        UpsertFeatureResponse with the feature details
    """
    try:
        feature = await features_service.upsert_feature(
            session=session,
            feature=request.feature,
            identifier_type=request.identifier_type,
            identifier=request.identifier,
            enabled=request.enabled,
        )

        if not feature:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upsert feature",
                headers={"Content-Type": "application/json"},
            )

        action = "enabled" if request.enabled else "disabled"
        return UpsertFeatureResponse(
            feature=request.feature,
            identifier_type=request.identifier_type,
            identifier=request.identifier,
            enabled=request.enabled,
            message=f"Feature '{request.feature}' has been {action} for {request.identifier_type.value} '{request.identifier}'",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error upserting feature: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upsert feature",
            headers={"Content-Type": "application/json"},
        )
