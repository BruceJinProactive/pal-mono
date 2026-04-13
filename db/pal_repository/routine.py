from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.routine import RoutineData, RoutineUpdateData
from db.tables.routine_executions import RoutineExecution
from db.tables.routine_items import RoutineItem
from db.tables.routine_schedules import RoutineSchedule
from db.tables.routines import Routine
from utils.log import logger


def _to_data(row: Routine) -> RoutineData:
    """Convert an ORM Routine to a RoutineData."""
    return RoutineData(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        category=row.category,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class RoutineRepository:
    """Async-only repository for Routine records.

    All methods return ``RoutineData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, routine_id: uuid.UUID) -> RoutineData | None:
        """Retrieve a single routine by its primary key."""
        try:
            result = await self.session.execute(
                select(Routine).filter(Routine.id == routine_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving routine by ID")
            raise

    async def list_by_project_id(self, project_id: uuid.UUID) -> list[RoutineData]:
        """List all routines belonging to a project."""
        try:
            result = await self.session.execute(
                select(Routine)
                .filter(Routine.project_id == project_id)
                .order_by(Routine.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            await self.session.rollback()
            logger.exception("Error listing routines by project ID")
            raise

    async def create(self, record: RoutineData) -> None:
        """Create a new routine.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = Routine(
                id=record.id,
                project_id=record.project_id,
                name=record.name,
                description=record.description,
                category=record.category,
                is_active=(record.is_active if record.is_active is not None else True),
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating routine: {e}")
            raise

    async def update(
        self,
        routine_id: uuid.UUID,
        record: RoutineUpdateData,
    ) -> None:
        """Update an existing routine.

        Fields from *record* that are non-None overwrite the existing values.
        """
        try:
            result = await self.session.execute(
                select(Routine).filter(Routine.id == routine_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return

            if record.name is not None:
                row.name = record.name
            if record.description is not None:
                row.description = record.description
            if record.category is not None:
                row.category = record.category
            if record.is_active is not None:
                row.is_active = record.is_active

            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error updating routine: {e}")
            raise

    async def delete(self, routine_id: uuid.UUID) -> RoutineData | None:
        """Delete a routine by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(Routine).filter(Routine.id == routine_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            data = _to_data(row)

            # Delete associated child records first (no DB-level cascade)
            await self.session.execute(
                delete(RoutineExecution).where(
                    RoutineExecution.routine_id == routine_id
                )
            )
            await self.session.execute(
                delete(RoutineSchedule).where(RoutineSchedule.routine_id == routine_id)
            )
            await self.session.execute(
                delete(RoutineItem).where(RoutineItem.routine_id == routine_id)
            )

            await self.session.delete(row)
            await self.session.commit()
            return data
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error deleting routine: {e}")
            raise
