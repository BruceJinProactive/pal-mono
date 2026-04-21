from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.affiliate import AffiliateData
from db.tables.affiliates import Affiliate
from utils.log import logger


def _to_data(row: Affiliate) -> AffiliateData:
    """Convert an ORM Affiliate to an AffiliateData."""
    return AffiliateData(
        id=row.id,
        rewardful_id=row.rewardful_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AffiliateRepository:
    """Async-only repository for Affiliate records.

    All methods return ``AffiliateData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, affiliate_id: uuid.UUID) -> AffiliateData | None:
        """Retrieve an affiliate by its primary key."""
        try:
            result = await self.session.execute(
                select(Affiliate).filter(Affiliate.id == affiliate_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving affiliate by ID")
            raise

    async def get_by_rewardful_id(self, rewardful_id: str) -> AffiliateData | None:
        """Retrieve an affiliate by Rewardful ID."""
        try:
            result = await self.session.execute(
                select(Affiliate).filter(Affiliate.rewardful_id == rewardful_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving affiliate by Rewardful ID")
            raise

    async def list_affiliates(
        self, limit: int = 100, offset: int = 0
    ) -> list[AffiliateData]:
        """List all affiliates with pagination.

        Args:
            limit: Number of records to return (1-1000, default 100).
            offset: Number of records to skip (>= 0, default 0).

        Raises:
            ValueError: If *limit* or *offset* is out of range.
        """
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        try:
            result = await self.session.execute(
                select(Affiliate).limit(limit).offset(offset)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing affiliates")
            raise

    async def get_by_rewardful_ids(
        self, rewardful_ids: list[str]
    ) -> dict[str, AffiliateData]:
        """Get multiple affiliates by Rewardful IDs (batch fetch)."""
        if not rewardful_ids:
            return {}
        try:
            result = await self.session.execute(
                select(Affiliate).filter(Affiliate.rewardful_id.in_(rewardful_ids))
            )
            rows = result.scalars().all()
            return {row.rewardful_id: _to_data(row) for row in rows}
        except Exception:
            logger.exception("Error retrieving affiliates by Rewardful IDs")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, rewardful_id: str) -> AffiliateData:
        """Create a new affiliate.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = Affiliate(rewardful_id=rewardful_id)
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating affiliate")
            raise

    async def delete(self, affiliate_id: uuid.UUID) -> bool:
        """Delete an affiliate by its ID.

        Returns True if deleted, False if not found.
        """
        try:
            result = await self.session.execute(
                select(Affiliate).filter(Affiliate.id == affiliate_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return False
            await self.session.delete(row)
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            logger.exception("Error deleting affiliate")
            raise
