from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.routine_execution import (
    RoutineExecutionData,
    RoutineExecutionUpdateData,
    _Unset,
)
from db.tables.routine_executions import RoutineExecution
from utils.log import logger


def _to_data(row: RoutineExecution) -> RoutineExecutionData:
    """Convert an ORM RoutineExecution to a RoutineExecutionData."""
    return RoutineExecutionData(
        id=row.id,
        routine_id=row.routine_id,
        schedule_id=row.schedule_id,
        scheduled_start=row.scheduled_start,
        scheduled_end=row.scheduled_end,
        status=row.status,
        assigned_user_id=row.assigned_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class RoutineExecutionRepository:
    """Async-only repository for RoutineExecution records.

    All methods return ``RoutineExecutionData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, execution_id: uuid.UUID) -> RoutineExecutionData | None:
        """Retrieve a single routine execution by its primary key."""
        try:
            result = await self.session.execute(
                select(RoutineExecution).filter(RoutineExecution.id == execution_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except SQLAlchemyError:
            logger.exception("Error retrieving routine execution by ID")
            raise

    async def list_by_routine_id(
        self, routine_id: uuid.UUID
    ) -> list[RoutineExecutionData]:
        """List all executions for a given routine."""
        try:
            result = await self.session.execute(
                select(RoutineExecution)
                .filter(RoutineExecution.routine_id == routine_id)
                .order_by(RoutineExecution.scheduled_start)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError:
            logger.exception("Error listing routine executions by routine ID")
            raise

    async def list_by_schedule_id(
        self, schedule_id: uuid.UUID
    ) -> list[RoutineExecutionData]:
        """List all executions for a given schedule."""
        try:
            result = await self.session.execute(
                select(RoutineExecution)
                .filter(RoutineExecution.schedule_id == schedule_id)
                .order_by(RoutineExecution.scheduled_start)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except SQLAlchemyError:
            logger.exception("Error listing routine executions by schedule ID")
            raise

    async def create(self, record: RoutineExecutionData) -> None:
        """Create a new routine execution.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = RoutineExecution(
                id=record.id,
                routine_id=record.routine_id,
                schedule_id=record.schedule_id,
                scheduled_start=record.scheduled_start,
                scheduled_end=record.scheduled_end,
                status=record.status,
                assigned_user_id=record.assigned_user_id,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating routine execution: {e}")
            raise

    async def update(
        self,
        execution_id: uuid.UUID,
        record: RoutineExecutionUpdateData,
    ) -> None:
        """Update an existing routine execution.

        Fields from *record* that are non-None overwrite the existing values.
        For ``assigned_user_id``, pass ``None`` to unassign; omit (``UNSET``)
        to leave unchanged.
        """
        try:
            result = await self.session.execute(
                select(RoutineExecution).filter(RoutineExecution.id == execution_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return

            if record.status is not None:
                row.status = record.status
            if record.scheduled_start is not None:
                row.scheduled_start = record.scheduled_start
            if record.scheduled_end is not None:
                row.scheduled_end = record.scheduled_end
            # Allow explicit unassignment (None) for nullable field
            if not isinstance(record.assigned_user_id, _Unset):
                row.assigned_user_id = record.assigned_user_id

            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating routine execution: {e}")
            raise

    async def delete(self, execution_id: uuid.UUID) -> RoutineExecutionData | None:
        """Delete a routine execution by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(RoutineExecution).filter(RoutineExecution.id == execution_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)
            await self.session.delete(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting routine execution: {e}")
            raise
