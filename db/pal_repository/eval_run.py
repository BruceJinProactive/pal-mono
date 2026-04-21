from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.eval_run import EvalRunData
from db.tables.eval_runs import EvalRun
from utils.log import logger


def _to_data(row: EvalRun) -> EvalRunData:
    """Convert an ORM EvalRun to an EvalRunData."""
    return EvalRunData(
        id=row.id,
        project_id=row.project_id,
        account_id=row.account_id,
        driver_mode=row.driver_mode,
        status=row.status,
        triggered_by=row.triggered_by,
        scenario_count=row.scenario_count,
        passed_count=row.passed_count,
        failed_count=row.failed_count,
        created_at=row.created_at,
        agent_fingerprint=row.agent_fingerprint,
        overall_score=row.overall_score,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_message=row.error_message,
        updated_at=row.updated_at,
    )


class EvalRunRepository:
    """Async-only repository for EvalRun records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, run_id: uuid.UUID) -> EvalRunData | None:
        """Retrieve an eval run by ID."""
        try:
            result = await self.session.execute(
                select(EvalRun).filter(EvalRun.id == run_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error getting eval run by ID")
            raise

    async def get_by_project(
        self,
        project_id: uuid.UUID,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[EvalRunData]:
        """Get all eval runs for a project with optional filters.

        Args:
            project_id: The project to query.
            status: Optional status string to filter by.
            start_date: If given, only runs with ``started_at >= start_date``
                are returned.  Runs where ``started_at`` is NULL (e.g. pending
                runs that have not started yet) are excluded.
            end_date: If given, only runs with ``started_at <= end_date`` are
                returned.
        """
        try:
            query = select(EvalRun).filter(EvalRun.project_id == project_id)
            if status is not None:
                query = query.filter(EvalRun.status == status)
            if start_date is not None:
                query = query.filter(EvalRun.started_at >= start_date)
            if end_date is not None:
                query = query.filter(EvalRun.started_at <= end_date)
            query = query.order_by(EvalRun.created_at.desc())
            result = await self.session.execute(query)
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error getting eval runs by project")
            raise

    async def create(self, record: EvalRunData) -> EvalRunData:
        """Create a new eval run."""
        try:
            row = EvalRun(
                id=record.id,
                project_id=record.project_id,
                account_id=record.account_id,
                agent_fingerprint=record.agent_fingerprint,
                driver_mode=record.driver_mode,
                status=record.status,
                triggered_by=record.triggered_by,
                scenario_count=record.scenario_count,
                passed_count=record.passed_count,
                failed_count=record.failed_count,
                overall_score=record.overall_score,
                started_at=record.started_at,
                completed_at=record.completed_at,
                error_message=record.error_message,
            )
            self.session.add(row)
            await self.session.flush()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating eval run")
            raise

    async def update_status(
        self,
        run_id: uuid.UUID,
        status: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> EvalRunData | None:
        """Update status and lifecycle timestamps of an eval run."""
        try:
            result = await self.session.execute(
                select(EvalRun).filter(EvalRun.id == run_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            row.status = status
            if started_at is not None:
                row.started_at = started_at
            if completed_at is not None:
                row.completed_at = completed_at
            if error_message is not None:
                row.error_message = error_message
            await self.session.flush()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error updating eval run status")
            raise
