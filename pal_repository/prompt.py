from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables.prompts import Prompt
from db.tables.types import Channel
from pal_repository.data_classes.prompt import PromptData
from utils.log import logger


def _to_data(row: Prompt) -> PromptData:
    """Convert an ORM Prompt to a PromptData.

    Enum fields are converted to their string values so the record does not
    expose ``db.tables.types`` to consumers.
    """
    return PromptData(
        id=row.id,
        name=row.name,
        resource_id=row.resource_id,
        resource_type=row.resource_type,
        deleted=row.deleted,
        created_at=row.created_at,
        updated_at=row.updated_at,
        default_prompt_id=row.default_prompt_id,
        channel=tuple(c.value for c in row.channel) if row.channel else (),
    )


class PromptRepository:
    """Async-only repository for Prompt records.

    All methods return ``PromptData`` — ORM objects never escape this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, prompt_id: uuid.UUID) -> PromptData | None:
        """Retrieve a single non-deleted prompt by primary key."""
        try:
            result = await self.session.execute(
                select(Prompt).filter(Prompt.id == prompt_id, ~Prompt.deleted)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception as e:
            logger.error(f"Error retrieving prompt by ID: {e}")
            raise

    async def list_by_resource(
        self,
        resource_type: str,
        resource_id: uuid.UUID,
    ) -> list[PromptData]:
        """List all non-deleted prompts for a given resource."""
        try:
            result = await self.session.execute(
                select(Prompt)
                .filter(
                    Prompt.resource_type == resource_type,
                    Prompt.resource_id == resource_id,
                    ~Prompt.deleted,
                )
                .order_by(Prompt.created_at.desc())
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception as e:
            logger.error(f"Error listing prompts by resource: {e}")
            raise

    async def create(self, record: PromptData) -> None:
        """Create a new prompt.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = Prompt(
                id=record.id,
                name=record.name,
                resource_id=record.resource_id,
                resource_type=record.resource_type,
                deleted=record.deleted,
                default_prompt_id=record.default_prompt_id,
                channel=(
                    [Channel(c) for c in record.channel] if record.channel else None
                ),
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating prompt: {e}")
            raise

    async def update(self, prompt_id: uuid.UUID, record: PromptData) -> None:
        """Update an existing prompt.

        All mutable fields from *record* are applied unconditionally so
        callers can clear nullable/list fields (e.g. ``default_prompt_id=None``,
        ``channel=()``).
        """
        try:
            result = await self.session.execute(
                select(Prompt).filter(Prompt.id == prompt_id, ~Prompt.deleted)
            )
            row = result.scalar_one_or_none()
            if not row:
                return

            row.name = record.name
            row.default_prompt_id = record.default_prompt_id
            row.channel = (
                [Channel(c) for c in record.channel] if record.channel else None
            )

            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating prompt: {e}")
            raise

    async def delete(self, prompt_id: uuid.UUID) -> PromptData | None:
        """Soft-delete a prompt by setting its deleted flag.

        Returns the prompt data as it was before deletion, or None if
        no matching non-deleted prompt was found.
        """
        try:
            result = await self.session.execute(
                select(Prompt).filter(Prompt.id == prompt_id, ~Prompt.deleted)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)
            row.deleted = True
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting prompt: {e}")
            raise
