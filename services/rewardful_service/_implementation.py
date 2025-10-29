import uuid
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.affiliate_repository import AffiliateRepositoryAsync
from db.tables import Affiliate
from services.rewardful_service._client import RewardfulClient
from utils.log import logger


class RewardfulService:
    """Service for managing affiliates with Rewardful integration."""

    def __init__(
        self, api_secret: str, base_url: str = "https://api.getrewardful.com/v1"
    ):
        """
        Initialize Rewardful service.

        Args:
            api_secret: Rewardful API secret
            base_url: Base URL for Rewardful API (defaults to production)
        """
        self.client = RewardfulClient(api_secret, base_url)

    async def create_affiliate(
        self,
        session: AsyncSession,
        email: str,
        first_name: str,
        last_name: str,
        campaign_id: str | None = None,
        token: str | None = None,
        stripe_customer_id: str | None = None,
        paypal_email: str | None = None,
        wise_email: str | None = None,
    ) -> tuple[Affiliate, Dict[str, Any]]:
        """
        Create affiliate in Rewardful and store locally.

        Args:
            session: Database session
            email: Affiliate email
            first_name: First name
            last_name: Last name
            campaign_id: Campaign ID (optional)
            token: Referral token (optional)
            stripe_customer_id: Stripe customer ID (optional)
            paypal_email: PayPal email (optional)
            wise_email: Wise email (optional)

        Returns:
            tuple[Affiliate, Dict]: Local affiliate record and Rewardful response
        """
        # Create affiliate in Rewardful
        rewardful_data = await self.client.create_affiliate(
            email=email,
            first_name=first_name,
            last_name=last_name,
            campaign_id=campaign_id,
            token=token,
            stripe_customer_id=stripe_customer_id,
            paypal_email=paypal_email,
            wise_email=wise_email,
        )

        # Store in local database
        repo = AffiliateRepositoryAsync(session)
        affiliate = await repo.create_affiliate(rewardful_id=rewardful_data["id"])

        logger.info(
            f"Created affiliate {affiliate.id} with Rewardful ID {rewardful_data['id']}"
        )
        return affiliate, rewardful_data

    async def get_affiliate(
        self,
        session: AsyncSession,
        affiliate_id: uuid.UUID,
        expand: List[str] | None = None,
    ) -> tuple[Affiliate, Dict[str, Any]] | None:
        """
        Get affiliate from database and fetch data from Rewardful.

        Args:
            session: Database session
            affiliate_id: Local affiliate ID
            expand: Fields to expand in Rewardful response

        Returns:
            tuple[Affiliate, Dict] | None: Local affiliate and Rewardful data, or None
        """
        repo = AffiliateRepositoryAsync(session)
        affiliate = await repo.get_affiliate_by_id(affiliate_id)

        if not affiliate:
            return None

        # Fetch full data from Rewardful
        rewardful_data = await self.client.get_affiliate(
            affiliate_id=affiliate.rewardful_id, expand=expand
        )
        return affiliate, rewardful_data

    async def get_affiliate_by_rewardful_id(
        self,
        session: AsyncSession,
        rewardful_id: str,
        expand: List[str] | None = None,
    ) -> tuple[Affiliate, Dict[str, Any]] | None:
        """
        Get affiliate by Rewardful ID.

        Args:
            session: Database session
            rewardful_id: Rewardful affiliate ID
            expand: Fields to expand in Rewardful response

        Returns:
            tuple[Affiliate, Dict] | None: Local affiliate and Rewardful data, or None
        """
        repo = AffiliateRepositoryAsync(session)
        affiliate = await repo.get_affiliate_by_rewardful_id(rewardful_id)

        if not affiliate:
            return None

        # Fetch full data from Rewardful
        rewardful_data = await self.client.get_affiliate(
            affiliate_id=rewardful_id, expand=expand
        )
        return affiliate, rewardful_data

    async def list_affiliates(
        self,
        session: AsyncSession,
        limit: int = 100,
        page: int = 1,
        campaign_id: str | None = None,
        expand: List[str] | None = None,
    ) -> Dict[str, Any]:
        """
        List affiliates from Rewardful.

        Args:
            session: Database session
            limit: Results per page
            page: Page number
            campaign_id: Filter by campaign
            expand: Fields to expand

        Returns:
            Dict: Paginated affiliate list from Rewardful
        """
        return await self.client.list_affiliates(
            limit=limit, page=page, campaign_id=campaign_id, expand=expand
        )

    async def update_affiliate(
        self,
        session: AsyncSession,
        affiliate_id: uuid.UUID,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        paypal_email: str | None = None,
        wise_email: str | None = None,
        state: str | None = None,
    ) -> tuple[Affiliate, Dict[str, Any]] | None:
        """
        Update affiliate in Rewardful.

        Args:
            session: Database session
            affiliate_id: Local affiliate ID
            email: New email (optional)
            first_name: New first name (optional)
            last_name: New last name (optional)
            paypal_email: New PayPal email (optional)
            wise_email: New Wise email (optional)
            state: Affiliate state: "active" or "disabled" (optional)

        Returns:
            tuple[Affiliate, Dict] | None: Local affiliate and updated Rewardful data
        """
        repo = AffiliateRepositoryAsync(session)
        affiliate = await repo.get_affiliate_by_id(affiliate_id)

        if not affiliate:
            return None

        # Update in Rewardful
        rewardful_data = await self.client.update_affiliate(
            affiliate_id=affiliate.rewardful_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            paypal_email=paypal_email,
            wise_email=wise_email,
            state=state,
        )

        logger.info(f"Updated affiliate {affiliate_id} in Rewardful")
        return affiliate, rewardful_data

    async def delete_affiliate(
        self, session: AsyncSession, affiliate_id: uuid.UUID
    ) -> bool:
        """
        Disable affiliate in Rewardful by setting state to "disabled".
        Note: Rewardful doesn't support actual deletion, and we keep the local record
        for historical tracking. The affiliate state in Rewardful is the source of truth.

        Args:
            session: Database session
            affiliate_id: Local affiliate ID

        Returns:
            bool: True if disabled, False if not found
        """
        repo = AffiliateRepositoryAsync(session)
        affiliate = await repo.get_affiliate_by_id(affiliate_id)

        if not affiliate:
            return False

        # Disable in Rewardful (set state to "disabled")
        await self.client.disable_affiliate(affiliate.rewardful_id)

        # Keep the local record - don't delete it
        # The state in Rewardful is the source of truth

        logger.info(
            f"Disabled affiliate {affiliate_id} in Rewardful (kept local record)"
        )
        return True
