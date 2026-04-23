from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.change_field import ChangeFieldData
from db.tables.change_log import ChangeField
from utils.log import logger


def _to_data(row: ChangeField) -> ChangeFieldData:
    """Convert an ORM ChangeField to a ChangeFieldData."""
    return ChangeFieldData(
        id=row.id,
        change_log_id=row.change_log_id,
        field=row.field,
        old_value=row.old_value,
        new_value=row.new_value,
    )


class ChangeFieldRepository:
    """Async-only repository for ChangeField records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_change_log_id(
        self, change_log_id: uuid.UUID
    ) -> list[ChangeFieldData]:
        """Retrieve all change fields for a given change log."""
        try:
            result = await self.session.execute(
                select(ChangeField).filter(ChangeField.change_log_id == change_log_id)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving change fields")
            raise
