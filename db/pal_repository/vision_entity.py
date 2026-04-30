from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.vision_entity import VisionEntityData
from db.tables import VisionEntity
from utils.log import logger


def _to_data(row: VisionEntity) -> VisionEntityData:
    return VisionEntityData(
        id=row.id,
        project_id=row.project_id,
        entity_type_id=row.entity_type_id,
        name=row.name,
        current_state_id=row.current_state_id,
        current_state_since=row.current_state_since,
        entity_metadata=dict(row.entity_metadata) if row.entity_metadata else {},
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class VisionEntityRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: VisionEntityData) -> None:
        try:
            row = VisionEntity(
                id=record.id,
                project_id=record.project_id,
                entity_type_id=record.entity_type_id,
                name=record.name,
                current_state_id=record.current_state_id,
                current_state_since=record.current_state_since,
                entity_metadata=record.entity_metadata,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Entity] DB error creating entity", exc_info=True)
            raise

    async def get_by_id(self, entity_id: uuid.UUID) -> VisionEntityData | None:
        try:
            result = await self.session.execute(
                select(VisionEntity).filter(VisionEntity.id == entity_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Entity] DB error getting entity by id", exc_info=True)
            return None

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        entity_type_id: uuid.UUID | None = None,
        current_state_id: uuid.UUID | None = None,
    ) -> list[VisionEntityData]:
        try:
            query = select(VisionEntity).filter(VisionEntity.project_id == project_id)
            if entity_type_id is not None:
                query = query.filter(VisionEntity.entity_type_id == entity_type_id)
            if current_state_id is not None:
                query = query.filter(VisionEntity.current_state_id == current_state_id)
            query = query.order_by(VisionEntity.created_at)
            result = await self.session.execute(query)
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Entity] DB error listing entities", exc_info=True)
            return []

    async def get_by_project_type_and_name(
        self,
        project_id: uuid.UUID,
        entity_type_id: uuid.UUID,
        name: str,
    ) -> VisionEntityData | None:
        try:
            result = await self.session.execute(
                select(VisionEntity).filter(
                    VisionEntity.project_id == project_id,
                    VisionEntity.entity_type_id == entity_type_id,
                    VisionEntity.name == name,
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error getting entity by name", exc_info=True
            )
            return None

    async def update(
        self, entity_id: uuid.UUID, **kwargs: object
    ) -> VisionEntityData | None:
        try:
            result = await self.session.execute(
                select(VisionEntity).filter(VisionEntity.id == entity_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None

            for key, value in kwargs.items():
                if hasattr(row, key):
                    setattr(row, key, value)

            res = _to_data(row)
            await self.session.commit()
            return res
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Entity] DB error updating entity", exc_info=True)
            raise

    async def delete(self, entity_id: uuid.UUID) -> bool:
        try:
            result = await self.session.execute(
                select(VisionEntity).filter(VisionEntity.id == entity_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return False

            await self.session.delete(row)
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Entity] DB error deleting entity", exc_info=True)
            raise
