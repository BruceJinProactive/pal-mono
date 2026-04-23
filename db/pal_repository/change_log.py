from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.pal_repository.data_classes.change_field import ChangeFieldData
from db.pal_repository.data_classes.change_log import ChangeLogData
from db.tables.change_log import ChangeField, ChangeLog
from utils.log import logger


def _field_to_data(row: ChangeField) -> ChangeFieldData:
    """Convert an ORM ChangeField to a ChangeFieldData."""
    return ChangeFieldData(
        id=row.id,
        change_log_id=row.change_log_id,
        field=row.field,
        old_value=row.old_value,
        new_value=row.new_value,
    )


def _to_data(row: ChangeLog) -> ChangeLogData:
    """Convert an ORM ChangeLog to a ChangeLogData."""
    return ChangeLogData(
        id=row.id,
        account_id=row.account_id,
        resource_type=row.resource_type.value if row.resource_type else "",
        resource_id=row.resource_id,
        author=row.author,
        action=row.action.value if row.action else "",
        created_at=row.created_at,
        fields=tuple(_field_to_data(f) for f in row.fields) if row.fields else (),
    )


class ChangeLogRepository:
    """Async-only repository for ChangeLog records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, log_id: uuid.UUID) -> ChangeLogData | None:
        """Retrieve a change log by ID with its fields."""
        try:
            result = await self.session.execute(
                select(ChangeLog)
                .options(selectinload(ChangeLog.fields))
                .filter(ChangeLog.id == log_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving change log by ID")
            raise

    async def get_by_resource(
        self, resource_type: str, resource_id: str
    ) -> list[ChangeLogData]:
        """Retrieve all change logs for a resource."""
        try:
            result = await self.session.execute(
                select(ChangeLog)
                .options(selectinload(ChangeLog.fields))
                .filter(
                    ChangeLog.resource_type == resource_type,
                    ChangeLog.resource_id == resource_id,
                )
                .order_by(ChangeLog.created_at.desc())
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError:
            await self.session.rollback()
            logger.exception("Error retrieving change logs by resource")
            raise
