from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.monitoring_run import MonitoringRunData
from db.tables.monitoring_runs import MonitoringRun
from utils.log import logger


def _to_data(row: MonitoringRun) -> MonitoringRunData:
    """Convert an ORM MonitoringRun to a MonitoringRunData."""
    return MonitoringRunData(
        id=row.id,
        monitoring_config_id=row.monitoring_config_id,
        started_at=row.started_at,
        trigger_metadata=dict(row.trigger_metadata) if row.trigger_metadata else {},
        evaluation_result=dict(row.evaluation_result) if row.evaluation_result else {},
        completed_at=row.completed_at,
        result=row.result,
        details=row.details,
        confidence=row.confidence,
        error_message=row.error_message,
    )


class MonitoringRunRepository:
    """Async-only repository for MonitoringRun records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, run_id: uuid.UUID) -> MonitoringRunData | None:
        """Retrieve a monitoring run by ID."""
        try:
            result = await self.session.execute(
                select(MonitoringRun).filter(MonitoringRun.id == run_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving monitoring run by ID")
            raise

    async def get_by_config_id(self, config_id: uuid.UUID) -> list[MonitoringRunData]:
        """Retrieve all runs for a monitoring config."""
        try:
            result = await self.session.execute(
                select(MonitoringRun)
                .filter(MonitoringRun.monitoring_config_id == config_id)
                .order_by(MonitoringRun.started_at.desc())
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving monitoring runs by config ID")
            raise
