import os
import uuid
from typing import List

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.admin import UserContext
from api.routes.admin._auth import authorize_admin
from api.schemas.admin.affiliate import (
    AffiliateResponse,
    CreateAffiliateRequest,
    UpdateAffiliateRequest,
)
from services.rewardful_service import RewardfulService
from utils.log import logger


def _get_rewardful_service() -> RewardfulService:
    """Get Rewardful service instance with configuration from environment."""
    api_secret = os.getenv("REWARDFUL_API_SECRET")
    if not api_secret:
        raise HTTPException(
            status_code=500, detail="Rewardful API secret not configured"
        )

    base_url = os.getenv("REWARDFUL_BASE_URL", "https://api.getrewardful.com/v1")
    return RewardfulService(api_secret, base_url)


async def create_affiliate(
    request: CreateAffiliateRequest,
    context: UserContext,
    session: AsyncSession,
) -> AffiliateResponse:
    """
    Create a new affiliate in Rewardful and store locally.

    Args:
        request: Affiliate creation request
        context: User context
        session: Database session

    Returns:
        AffiliateResponse: Created affiliate data
    """
    authorize_admin(context)
    service = _get_rewardful_service()

    try:
        affiliate, rewardful_data = await service.create_affiliate(
            session=session,
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            campaign_id=request.campaign_id,
            token=request.token,
            stripe_customer_id=request.stripe_customer_id,
            paypal_email=request.paypal_email,
            wise_email=request.wise_email,
        )

        return AffiliateResponse(
            id=affiliate.id,
            rewardful_id=affiliate.rewardful_id,
            rewardful_data=rewardful_data,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating affiliate: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create affiliate. Please check the logs or contact support.",
        )


async def get_affiliate(
    affiliate_id: uuid.UUID,
    context: UserContext,
    session: AsyncSession,
    expand: List[str] | None = None,
) -> AffiliateResponse:
    """
    Get affiliate by ID with data from Rewardful.

    Args:
        affiliate_id: Local affiliate ID
        context: User context
        session: Database session
        expand: Fields to expand from Rewardful (campaign, links, coupon)

    Returns:
        AffiliateResponse: Affiliate data

    Raises:
        HTTPException: If affiliate not found
    """
    authorize_admin(context)
    service = _get_rewardful_service()

    try:
        result = await service.get_affiliate(
            session=session, affiliate_id=affiliate_id, expand=expand
        )

        if not result:
            raise HTTPException(status_code=404, detail="Affiliate not found")

        affiliate, rewardful_data = result

        return AffiliateResponse(
            id=affiliate.id,
            rewardful_id=affiliate.rewardful_id,
            rewardful_data=rewardful_data,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving affiliate: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve affiliate")


async def list_affiliates(
    context: UserContext,
    session: AsyncSession,
    limit: int = 100,
    page: int = 1,
    campaign_id: str | None = None,
    expand: List[str] | None = None,
) -> dict:
    """
    List affiliates from Rewardful.

    Args:
        context: User context
        session: Database session
        limit: Results per page (max 100)
        page: Page number
        campaign_id: Filter by campaign ID
        expand: Fields to expand

    Returns:
        dict: Paginated affiliate list from Rewardful
    """
    authorize_admin(context)
    service = _get_rewardful_service()

    try:
        return await service.list_affiliates(
            session=session,
            limit=min(limit, 100),  # Enforce max 100
            page=page,
            campaign_id=campaign_id,
            expand=expand,
        )
    except Exception as e:
        logger.error(f"Error listing affiliates: {e}")
        raise HTTPException(status_code=500, detail="Failed to list affiliates")


async def update_affiliate(
    affiliate_id: uuid.UUID,
    request: UpdateAffiliateRequest,
    context: UserContext,
    session: AsyncSession,
) -> AffiliateResponse:
    """
    Update affiliate in Rewardful.

    Args:
        affiliate_id: Local affiliate ID
        request: Update request
        context: User context
        session: Database session

    Returns:
        AffiliateResponse: Updated affiliate data

    Raises:
        HTTPException: If affiliate not found
    """
    authorize_admin(context)
    service = _get_rewardful_service()

    try:
        result = await service.update_affiliate(
            session=session,
            affiliate_id=affiliate_id,
            email=request.email,
            first_name=request.first_name,
            last_name=request.last_name,
            paypal_email=request.paypal_email,
            wise_email=request.wise_email,
            state=request.state,
        )

        if not result:
            raise HTTPException(status_code=404, detail="Affiliate not found")

        affiliate, rewardful_data = result

        return AffiliateResponse(
            id=affiliate.id,
            rewardful_id=affiliate.rewardful_id,
            rewardful_data=rewardful_data,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating affiliate: {e}")
        raise HTTPException(status_code=500, detail="Failed to update affiliate")


async def delete_affiliate(
    affiliate_id: uuid.UUID,
    context: UserContext,
    session: AsyncSession,
) -> dict:
    """
    Disable affiliate in Rewardful (sets state to "disabled").
    Note: Rewardful doesn't support actual deletion, so the affiliate is disabled instead.
    The local database record is kept for historical tracking.

    Args:
        affiliate_id: Local affiliate ID
        context: User context
        session: Database session

    Returns:
        dict: Success message

    Raises:
        HTTPException: If affiliate not found
    """
    authorize_admin(context)
    service = _get_rewardful_service()

    try:
        deleted = await service.delete_affiliate(
            session=session, affiliate_id=affiliate_id
        )

        if not deleted:
            raise HTTPException(status_code=404, detail="Affiliate not found")

        return {
            "message": "Affiliate disabled successfully (state set to 'disabled' in Rewardful)"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting affiliate: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete affiliate")
