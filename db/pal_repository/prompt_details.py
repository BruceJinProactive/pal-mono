from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.prompt_details import PromptDetailsData
from db.tables.prompts import PromptDetails
from utils.log import logger


def _to_data(row: PromptDetails) -> PromptDetailsData:
    """Convert an ORM PromptDetails to a PromptDetailsData."""
    return PromptDetailsData(
        id=row.id,
        prompt_id=row.prompt_id,
        version_number=row.version_number,
        content=row.content,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        change_summary=row.change_summary,
    )


class PromptDetailsRepository:
    """Async-only repository for PromptDetails (versioned prompt content).

    All methods return ``PromptDetailsData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_latest(self, prompt_id: uuid.UUID) -> PromptDetailsData | None:
        """Retrieve the latest version of prompt details for a given prompt."""
        try:
            result = await self.session.execute(
                select(PromptDetails)
                .filter(PromptDetails.prompt_id == prompt_id)
                .order_by(PromptDetails.version_number.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving latest prompt details: {e}")
            raise

    async def list_by_prompt_id(self, prompt_id: uuid.UUID) -> list[PromptDetailsData]:
        """List all versions of prompt details, newest first."""
        try:
            result = await self.session.execute(
                select(PromptDetails)
                .filter(PromptDetails.prompt_id == prompt_id)
                .order_by(PromptDetails.version_number.desc())
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception as e:
            logger.error(f"Error listing prompt details: {e}")
            raise

    async def create(self, record: PromptDetailsData) -> None:
        """Create a new prompt details (version) record.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = PromptDetails(
                id=record.id,
                prompt_id=record.prompt_id,
                version_number=record.version_number,
                content=record.content,
                created_by=record.created_by,
                change_summary=record.change_summary,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating prompt details: {e}")
            raise
