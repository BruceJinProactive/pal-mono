import uuid
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import Affiliate
from utils.log import logger


class AffiliateRepositoryAsync:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_affiliate(self, rewardful_id: str) -> Affiliate:
        """
        Create a new affiliate.

        Args:
            rewardful_id: The Rewardful affiliate ID

        Returns:
            Affiliate: The created affiliate object
        """
        try:
            affiliate = Affiliate(rewardful_id=rewardful_id)
            self.session.add(affiliate)
            await self.session.commit()
            await self.session.refresh(affiliate)
            return affiliate
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating affiliate: {e}")
            raise

    async def get_affiliate_by_id(self, affiliate_id: uuid.UUID) -> Affiliate | None:
        """
        Get affiliate by internal ID.

        Args:
            affiliate_id: The internal affiliate ID

        Returns:
            Affiliate | None: The affiliate if found, None otherwise
        """
        try:
            query = select(Affiliate).filter(Affiliate.id == affiliate_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving affiliate by ID {affiliate_id}: {e}")
            raise

    async def get_affiliate_by_rewardful_id(
        self, rewardful_id: str
    ) -> Affiliate | None:
        """
        Get affiliate by Rewardful ID.

        Args:
            rewardful_id: The Rewardful affiliate ID

        Returns:
            Affiliate | None: The affiliate if found, None otherwise
        """
        try:
            query = select(Affiliate).filter(Affiliate.rewardful_id == rewardful_id)
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving affiliate by Rewardful ID {rewardful_id}: {e}"
            )
            raise

    async def list_affiliates(
        self, limit: int = 100, offset: int = 0
    ) -> List[Affiliate]:
        """
        List all affiliates with pagination.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List[Affiliate]: List of affiliates
        """
        try:
            query = select(Affiliate).limit(limit).offset(offset)
            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error listing affiliates: {e}")
            raise

    async def get_affiliates_by_rewardful_ids(
        self, rewardful_ids: List[str]
    ) -> Dict[str, Affiliate]:
        """
        Get multiple affiliates by Rewardful IDs in a single query.
        Batch fetching to avoid N+1 query problem.

        Args:
            rewardful_ids: List of Rewardful affiliate IDs

        Returns:
            Dict[str, Affiliate]: Map of rewardful_id -> Affiliate
        """
        try:
            if not rewardful_ids:
                return {}

            query = select(Affiliate).filter(Affiliate.rewardful_id.in_(rewardful_ids))
            result = await self.session.execute(query)
            affiliates = result.scalars().all()
            return {aff.rewardful_id: aff for aff in affiliates}
        except SQLAlchemyError as e:
            logger.error(f"Error retrieving affiliates by Rewardful IDs: {e}")
            raise

    async def delete_affiliate(self, affiliate_id: uuid.UUID) -> bool:
        """
        Delete an affiliate.

        Args:
            affiliate_id: The affiliate ID

        Returns:
            bool: True if deleted, False if not found
        """
        try:
            affiliate = await self.get_affiliate_by_id(affiliate_id)
            if not affiliate:
                return False

            await self.session.delete(affiliate)
            await self.session.commit()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting affiliate {affiliate_id}: {e}")
            raise
