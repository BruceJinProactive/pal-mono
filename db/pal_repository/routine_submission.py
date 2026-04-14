from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.routine_submission import RoutineSubmissionData
from db.tables.routine_submissions import RoutineSubmission
from db.tables.types import SubmissionStatus
from utils.log import logger


def _to_data(row: RoutineSubmission) -> RoutineSubmissionData:
    """Convert an ORM RoutineSubmission to a RoutineSubmissionData."""
    return RoutineSubmissionData(
        id=row.id,
        execution_id=row.execution_id,
        status=row.status.value if row.status else "",
        submitted_by=row.submitted_by,
        submitted_at=row.submitted_at,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        review_notes=row.review_notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class RoutineSubmissionRepository:
    """Async-only repository for RoutineSubmission records.

    All methods return ``RoutineSubmissionData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, submission_id: uuid.UUID) -> RoutineSubmissionData | None:
        """Retrieve a single submission by its primary key."""
        try:
            result = await self.session.execute(
                select(RoutineSubmission).filter(RoutineSubmission.id == submission_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving routine submission by ID")
            raise

    async def get_by_execution_id(
        self, execution_id: uuid.UUID
    ) -> RoutineSubmissionData | None:
        """Retrieve the submission for a given execution (1:1 relationship)."""
        try:
            result = await self.session.execute(
                select(RoutineSubmission).filter(
                    RoutineSubmission.execution_id == execution_id
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving routine submission by execution ID")
            raise

    async def list_by_status(self, status: str) -> list[RoutineSubmissionData]:
        """List all submissions with a given status."""
        try:
            result = await self.session.execute(
                select(RoutineSubmission)
                .filter(RoutineSubmission.status == SubmissionStatus(status))
                .order_by(RoutineSubmission.created_at)
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing routine submissions by status")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, record: RoutineSubmissionData) -> None:
        """Create a new routine submission.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = RoutineSubmission(
                id=record.id,
                execution_id=record.execution_id,
                status=SubmissionStatus(record.status),
                submitted_by=record.submitted_by,
                submitted_at=record.submitted_at,
                reviewed_by=record.reviewed_by,
                reviewed_at=record.reviewed_at,
                review_notes=record.review_notes,
                created_at=record.created_at,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating routine submission: {e}")
            raise

    async def delete(self, submission_id: uuid.UUID) -> RoutineSubmissionData | None:
        """Delete a routine submission by its ID.

        Returns the deleted record, or None if no match was found.

        Raises:
            Exception: If the delete fails.
        """
        try:
            result = await self.session.execute(
                select(RoutineSubmission).filter(RoutineSubmission.id == submission_id)
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
            logger.error(f"Error deleting routine submission: {e}")
            raise
