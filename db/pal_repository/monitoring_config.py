from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.monitoring_config import MonitoringConfigData
from db.tables.monitoring_configs import MonitoringConfig
from utils.log import logger


def _to_data(row: MonitoringConfig) -> MonitoringConfigData:
    """Convert an ORM MonitoringConfig to a MonitoringConfigData."""
    return MonitoringConfigData(
        id=row.id,
        project_id=row.project_id,
        signal_source_id=row.signal_source_id,
        name=row.name,
        enabled=row.enabled,
        created_at=row.created_at,
        description=row.description,
        rules=dict(row.rules) if row.rules else {},
        tags=tuple(row.tags) if row.tags else (),
        updated_at=row.updated_at,
    )


class MonitoringConfigRepository:
    """Async-only repository for MonitoringConfig records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, config_id: uuid.UUID) -> MonitoringConfigData | None:
        """Retrieve a monitoring config by ID."""
        try:
            result = await self.session.execute(
                select(MonitoringConfig).filter(MonitoringConfig.id == config_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving monitoring config by ID")
            raise

    async def get_by_project_id(
        self, project_id: uuid.UUID
    ) -> list[MonitoringConfigData]:
        """Retrieve all monitoring configs for a project."""
        try:
            result = await self.session.execute(
                select(MonitoringConfig).filter(
                    MonitoringConfig.project_id == project_id
                )
            )
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            await self.session.rollback()
            logger.exception("Error retrieving monitoring configs by project")
            raise
