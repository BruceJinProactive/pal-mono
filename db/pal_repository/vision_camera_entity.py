from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.vision_camera_entity import VisionCameraEntityData
from db.tables import VisionCameraEntity
from utils.log import logger


def _to_data(row: VisionCameraEntity) -> VisionCameraEntityData:
    return VisionCameraEntityData(
        id=row.id,
        camera_config_id=row.camera_config_id,
        entity_id=row.entity_id,
        roi_hint=dict(row.roi_hint) if row.roi_hint else None,
        created_at=row.created_at,
    )


class VisionCameraEntityRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: VisionCameraEntityData) -> None:
        try:
            row = VisionCameraEntity(
                id=record.id,
                camera_config_id=record.camera_config_id,
                entity_id=record.entity_id,
                roi_hint=record.roi_hint,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Config] DB error creating camera-entity mapping",
                exc_info=True,
            )
            raise

    async def get_by_id(self, mapping_id: uuid.UUID) -> VisionCameraEntityData | None:
        try:
            result = await self.session.execute(
                select(VisionCameraEntity).filter(VisionCameraEntity.id == mapping_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Config] DB error getting camera-entity mapping by id",
                exc_info=True,
            )
            return None

    async def get_by_camera_and_entity(
        self, camera_config_id: uuid.UUID, entity_id: uuid.UUID
    ) -> VisionCameraEntityData | None:
        try:
            result = await self.session.execute(
                select(VisionCameraEntity).filter(
                    VisionCameraEntity.camera_config_id == camera_config_id,
                    VisionCameraEntity.entity_id == entity_id,
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Config] DB error getting camera-entity mapping by pair",
                exc_info=True,
            )
            return None

    async def list_by_camera(
        self, camera_config_id: uuid.UUID
    ) -> list[VisionCameraEntityData]:
        try:
            result = await self.session.execute(
                select(VisionCameraEntity)
                .filter(VisionCameraEntity.camera_config_id == camera_config_id)
                .order_by(VisionCameraEntity.created_at)
            )
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Config] DB error listing entities for camera",
                exc_info=True,
            )
            return []

    async def list_by_entity(
        self, entity_id: uuid.UUID
    ) -> list[VisionCameraEntityData]:
        try:
            result = await self.session.execute(
                select(VisionCameraEntity)
                .filter(VisionCameraEntity.entity_id == entity_id)
                .order_by(VisionCameraEntity.created_at)
            )
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Config] DB error listing cameras for entity",
                exc_info=True,
            )
            return []

    async def update(
        self, mapping_id: uuid.UUID, **kwargs: object
    ) -> VisionCameraEntityData | None:
        try:
            result = await self.session.execute(
                select(VisionCameraEntity).filter(VisionCameraEntity.id == mapping_id)
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
            logger.error(
                "[Vision Config] DB error updating camera-entity mapping",
                exc_info=True,
            )
            raise

    async def delete(self, mapping_id: uuid.UUID) -> bool:
        try:
            result = await self.session.execute(
                select(VisionCameraEntity).filter(VisionCameraEntity.id == mapping_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return False

            await self.session.delete(row)
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Config] DB error deleting camera-entity mapping",
                exc_info=True,
            )
            raise
