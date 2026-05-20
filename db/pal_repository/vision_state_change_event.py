from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.vision_state_change_event import (
    VisionStateChangeEventData,
)
from db.tables import Project, VisionEntity, VisionStateChangeEvent
from utils.log import logger


def _to_data(row: VisionStateChangeEvent) -> VisionStateChangeEventData:
    return VisionStateChangeEventData(
        id=row.id,
        entity_id=row.entity_id,
        new_state_id=row.new_state_id,
        observed_at=row.observed_at,
        event_metadata=dict(row.event_metadata) if row.event_metadata else {},
        camera_config_id=row.camera_config_id,
        previous_state_id=row.previous_state_id,
        confidence=row.confidence,
        frame_s3_key=row.frame_s3_key,
    )


class VisionStateChangeEventRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: VisionStateChangeEventData) -> None:
        try:
            row = VisionStateChangeEvent(
                id=record.id,
                entity_id=record.entity_id,
                new_state_id=record.new_state_id,
                observed_at=record.observed_at,
                event_metadata=record.event_metadata,
                camera_config_id=record.camera_config_id,
                previous_state_id=record.previous_state_id,
                confidence=record.confidence,
                frame_s3_key=record.frame_s3_key,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision StateChangeEvent] DB error creating event", exc_info=True
            )
            raise

    async def get_by_id(self, event_id: uuid.UUID) -> VisionStateChangeEventData | None:
        try:
            result = await self.session.execute(
                select(VisionStateChangeEvent).filter(
                    VisionStateChangeEvent.id == event_id
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision StateChangeEvent] DB error getting event by id", exc_info=True
            )
            return None

    async def get_by_id_for_account(
        self, event_id: uuid.UUID, account_id: uuid.UUID
    ) -> VisionStateChangeEventData | None:
        try:
            result = await self.session.execute(
                select(VisionStateChangeEvent)
                .join(
                    VisionEntity,
                    VisionStateChangeEvent.entity_id == VisionEntity.id,
                )
                .join(
                    Project,
                    VisionEntity.project_id == Project.id,
                )
                .filter(
                    VisionStateChangeEvent.id == event_id,
                    Project.account_id == account_id,
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision StateChangeEvent] DB error getting event by id for account",
                exc_info=True,
            )
            return None

    async def list_by_account(
        self,
        account_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        entity_id: uuid.UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[VisionStateChangeEventData]:
        try:
            query = (
                select(VisionStateChangeEvent)
                .join(
                    VisionEntity,
                    VisionStateChangeEvent.entity_id == VisionEntity.id,
                )
                .join(
                    Project,
                    VisionEntity.project_id == Project.id,
                )
                .filter(Project.account_id == account_id)
            )
            if project_id is not None:
                query = query.filter(VisionEntity.project_id == project_id)
            if entity_id is not None:
                query = query.filter(VisionStateChangeEvent.entity_id == entity_id)
            if start is not None:
                query = query.filter(VisionStateChangeEvent.observed_at >= start)
            if end is not None:
                query = query.filter(VisionStateChangeEvent.observed_at <= end)
            query = query.order_by(VisionStateChangeEvent.observed_at.desc()).limit(
                limit
            )
            result = await self.session.execute(query)
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision StateChangeEvent] DB error listing events", exc_info=True
            )
            return []

    async def update_metadata(
        self,
        event_id: uuid.UUID,
        observed_at: datetime,
        metadata: dict[str, Any],
    ) -> bool:
        try:
            result = await self.session.execute(
                update(VisionStateChangeEvent)
                .where(
                    VisionStateChangeEvent.id == event_id,
                    VisionStateChangeEvent.observed_at == observed_at,
                )
                .values(event_metadata=metadata)
            )
            await self.session.commit()
            return (result.rowcount or 0) > 0
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision StateChangeEvent] DB error updating metadata", exc_info=True
            )
            raise

    async def delete(self, event_id: uuid.UUID) -> bool:
        try:
            result = await self.session.execute(
                delete(VisionStateChangeEvent).where(
                    VisionStateChangeEvent.id == event_id
                )
            )
            await self.session.commit()
            return (result.rowcount or 0) > 0
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision StateChangeEvent] DB error deleting event", exc_info=True
            )
            raise

    async def delete_for_account(
        self, event_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        try:
            subquery = (
                select(VisionStateChangeEvent.id)
                .join(
                    VisionEntity,
                    VisionStateChangeEvent.entity_id == VisionEntity.id,
                )
                .join(
                    Project,
                    VisionEntity.project_id == Project.id,
                )
                .filter(
                    VisionStateChangeEvent.id == event_id,
                    Project.account_id == account_id,
                )
            )
            result = await self.session.execute(
                delete(VisionStateChangeEvent).where(
                    VisionStateChangeEvent.id.in_(subquery)
                )
            )
            await self.session.commit()
            return (result.rowcount or 0) > 0
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision StateChangeEvent] DB error deleting event for account",
                exc_info=True,
            )
            raise

    async def list_test_events_by_config(
        self,
        camera_config_id: uuid.UUID,
        limit: int = 100,
    ) -> list[VisionStateChangeEventData]:
        try:
            query = (
                select(VisionStateChangeEvent)
                .filter(
                    VisionStateChangeEvent.camera_config_id == camera_config_id,
                    VisionStateChangeEvent.event_metadata["is_test"]
                    .as_boolean()
                    .is_(True),
                )
                .order_by(VisionStateChangeEvent.observed_at.desc())
                .limit(limit)
            )
            result = await self.session.execute(query)
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision StateChangeEvent] DB error listing test events by config",
                exc_info=True,
            )
            return []

    async def verify_entity_belongs_to_account(
        self, entity_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        try:
            result = await self.session.execute(
                select(VisionEntity.id)
                .join(Project, VisionEntity.project_id == Project.id)
                .filter(
                    VisionEntity.id == entity_id,
                    Project.account_id == account_id,
                )
            )
            return result.scalar_one_or_none() is not None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision StateChangeEvent] DB error verifying entity ownership",
                exc_info=True,
            )
            return False
