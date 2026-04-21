from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.campaign import CampaignData, CampaignMessageData
from db.tables.campaigns import Campaign, CampaignChannel, CampaignMessage
from utils.log import logger


def _to_data(row: Campaign) -> CampaignData:
    """Convert an ORM Campaign to a CampaignData."""
    return CampaignData(
        id=row.id,
        account_id=row.account_id,
        name=row.name,
        message=row.message,
        channel=row.channel.value,
        internal_recipient=row.internal_recipient,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _msg_to_data(row: CampaignMessage) -> CampaignMessageData:
    """Convert an ORM CampaignMessage to a CampaignMessageData."""
    return CampaignMessageData(
        id=row.id,
        campaign_id=row.campaign_id,
        recipient=row.recipient,
        status=row.status.value,
        created_at=row.created_at,
        error_detail=row.error_detail,
        updated_at=row.updated_at,
    )


class CampaignRepository:
    """Async-only repository for Campaign records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, campaign_id: uuid.UUID) -> CampaignData | None:
        """Retrieve a campaign by ID."""
        try:
            result = await self.session.execute(
                select(Campaign).filter(Campaign.id == campaign_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving campaign by ID")
            raise

    async def get_by_account_id(
        self, account_id: uuid.UUID, skip: int = 0, limit: int = 20
    ) -> tuple[list[CampaignData], int]:
        """Retrieve campaigns for an account with pagination.

        Args:
            account_id: The account to query.
            skip: Number of records to skip (>= 0, default 0).
            limit: Number of records to return (1-1000, default 20).

        Raises:
            ValueError: If *skip* or *limit* is out of range.
        """
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        if skip < 0:
            raise ValueError("skip must be >= 0")
        try:
            count_result = await self.session.execute(
                select(func.count())
                .select_from(Campaign)
                .filter(Campaign.account_id == account_id)
            )
            total = count_result.scalar() or 0
            result = await self.session.execute(
                select(Campaign)
                .filter(Campaign.account_id == account_id)
                .order_by(Campaign.created_at.desc(), Campaign.id.desc())
                .offset(skip)
                .limit(limit)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows], total
        except Exception:
            logger.exception("Error retrieving campaigns by account")
            raise

    async def create(self, record: CampaignData) -> CampaignData:
        """Create a new campaign."""
        row = Campaign(
            id=record.id,
            account_id=record.account_id,
            name=record.name,
            message=record.message,
            channel=CampaignChannel(record.channel),
            internal_recipient=record.internal_recipient,
        )
        self.session.add(row)

        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating campaign")
            raise

        await self.session.refresh(row)
        return _to_data(row)
