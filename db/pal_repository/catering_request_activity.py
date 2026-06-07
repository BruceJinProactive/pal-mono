from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.catering_request_activity import (
    CateringRequestActivityData,
)
from db.tables import CateringRequestActivity
from db.tables.catering_request_activities import (
    CateringRequestActivityActorType,
    CateringRequestActivitySource,
    CateringRequestActivityType,
)
from utils.log import logger


def _to_data(row: CateringRequestActivity) -> CateringRequestActivityData:
    return CateringRequestActivityData(
        id=row.id,
        catering_request_id=row.catering_request_id,
        project_id=row.project_id,
        activity_type=row.activity_type,
        actor_type=row.actor_type,
        actor_id=row.actor_id,
        actor_display_name=row.actor_display_name,
        description=row.description,
        metadata=dict(row.activity_metadata) if row.activity_metadata else {},
        schema_version=row.schema_version,
        source=row.source,
        occurred_at=row.occurred_at,
        created_at=row.created_at,
    )


class CateringRequestActivityRepository:
    """Async repository for catering request activity timeline records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, record: CateringRequestActivityData
    ) -> CateringRequestActivityData:
        try:
            row = CateringRequestActivity(
                id=record.id,
                catering_request_id=record.catering_request_id,
                project_id=record.project_id,
                activity_type=record.activity_type,
                actor_type=record.actor_type,
                actor_id=record.actor_id,
                actor_display_name=record.actor_display_name,
                description=record.description,
                activity_metadata=dict(record.metadata),
                schema_version=record.schema_version,
                source=record.source,
                occurred_at=record.occurred_at,
                created_at=record.created_at,
            )
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("[catering] DB error creating request activity")
            raise

    async def list_by_request(
        self,
        project_id: uuid.UUID,
        catering_request_id: uuid.UUID,
        limit: int = 50,
        before: datetime | None = None,
    ) -> list[CateringRequestActivityData]:
        try:
            query = select(CateringRequestActivity).filter(
                CateringRequestActivity.project_id == project_id,
                CateringRequestActivity.catering_request_id == catering_request_id,
            )
            if before is not None:
                query = query.filter(CateringRequestActivity.occurred_at < before)

            query = query.order_by(CateringRequestActivity.occurred_at.desc()).limit(
                limit
            )
            result = await self.session.execute(query)
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.exception("[catering] DB error listing request activities")
            raise


__all__ = [
    "CateringRequestActivityActorType",
    "CateringRequestActivityData",
    "CateringRequestActivityRepository",
    "CateringRequestActivitySource",
    "CateringRequestActivityType",
]
