from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.vision_camera_configuration import (
    VisionCameraConfigurationData,
)
from db.tables import VisionCameraConfiguration
from utils.log import logger


def _to_data(row: VisionCameraConfiguration) -> VisionCameraConfigurationData:
    return VisionCameraConfigurationData(
        id=row.id,
        signal_source_id=row.signal_source_id,
        project_id=row.project_id,
        name=row.name,
        llm_prompt=row.llm_prompt,
        llm_provider=row.llm_provider,
        llm_model=row.llm_model,
        processing_interval_seconds=row.processing_interval_seconds,
        reference_images=list(row.reference_images) if row.reference_images else [],
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class VisionCameraConfigurationRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: VisionCameraConfigurationData) -> None:
        try:
            row = VisionCameraConfiguration(
                id=record.id,
                signal_source_id=record.signal_source_id,
                project_id=record.project_id,
                name=record.name,
                llm_prompt=record.llm_prompt,
                llm_provider=record.llm_provider,
                llm_model=record.llm_model,
                processing_interval_seconds=record.processing_interval_seconds,
                reference_images=record.reference_images,
                enabled=record.enabled,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Config] DB error creating camera config", exc_info=True
            )
            raise

    async def get_by_id(
        self, config_id: uuid.UUID
    ) -> VisionCameraConfigurationData | None:
        try:
            result = await self.session.execute(
                select(VisionCameraConfiguration).filter(
                    VisionCameraConfiguration.id == config_id
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Config] DB error getting camera config by id", exc_info=True
            )
            return None

    async def get_by_signal_source(
        self, signal_source_id: uuid.UUID
    ) -> VisionCameraConfigurationData | None:
        try:
            result = await self.session.execute(
                select(VisionCameraConfiguration).filter(
                    VisionCameraConfiguration.signal_source_id == signal_source_id
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Config] DB error getting camera config by source",
                exc_info=True,
            )
            return None

    async def list_by_project(
        self, project_id: uuid.UUID
    ) -> list[VisionCameraConfigurationData]:
        try:
            result = await self.session.execute(
                select(VisionCameraConfiguration)
                .filter(VisionCameraConfiguration.project_id == project_id)
                .order_by(VisionCameraConfiguration.created_at)
            )
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Config] DB error listing camera configs", exc_info=True
            )
            return []

    async def update(
        self, config_id: uuid.UUID, **kwargs: object
    ) -> VisionCameraConfigurationData | None:
        try:
            result = await self.session.execute(
                select(VisionCameraConfiguration).filter(
                    VisionCameraConfiguration.id == config_id
                )
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
                "[Vision Config] DB error updating camera config", exc_info=True
            )
            raise

    async def delete(self, config_id: uuid.UUID) -> bool:
        try:
            result = await self.session.execute(
                select(VisionCameraConfiguration).filter(
                    VisionCameraConfiguration.id == config_id
                )
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
                "[Vision Config] DB error deleting camera config", exc_info=True
            )
            raise
