from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.vision_entity_state_definition import (
    VisionEntityStateDefinitionData,
)
from db.tables import VisionEntityStateDefinition
from utils.log import logger


def _to_data(
    row: VisionEntityStateDefinition,
) -> VisionEntityStateDefinitionData:
    return VisionEntityStateDefinitionData(
        id=row.id,
        entity_type_id=row.entity_type_id,
        name=row.name,
        display_name=row.display_name,
        color=row.color,
        sort_order=row.sort_order,
        is_default=row.is_default,
        created_at=row.created_at,
        criteria=row.criteria,
    )


class VisionEntityStateDefinitionRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: VisionEntityStateDefinitionData) -> None:
        try:
            row = VisionEntityStateDefinition(
                id=record.id,
                entity_type_id=record.entity_type_id,
                name=record.name,
                display_name=record.display_name,
                color=record.color,
                sort_order=record.sort_order,
                is_default=record.is_default,
                criteria=record.criteria,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error creating state definition", exc_info=True
            )
            raise

    async def get_by_id(
        self, state_definition_id: uuid.UUID
    ) -> VisionEntityStateDefinitionData | None:
        try:
            result = await self.session.execute(
                select(VisionEntityStateDefinition).filter(
                    VisionEntityStateDefinition.id == state_definition_id
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error getting state definition by id",
                exc_info=True,
            )
            return None

    async def list_by_entity_type(
        self, entity_type_id: uuid.UUID
    ) -> list[VisionEntityStateDefinitionData]:
        try:
            result = await self.session.execute(
                select(VisionEntityStateDefinition)
                .filter(VisionEntityStateDefinition.entity_type_id == entity_type_id)
                .order_by(VisionEntityStateDefinition.sort_order)
            )
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error listing state definitions",
                exc_info=True,
            )
            return []

    async def get_by_entity_type_and_name(
        self, entity_type_id: uuid.UUID, name: str
    ) -> VisionEntityStateDefinitionData | None:
        try:
            result = await self.session.execute(
                select(VisionEntityStateDefinition).filter(
                    VisionEntityStateDefinition.entity_type_id == entity_type_id,
                    VisionEntityStateDefinition.name == name,
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error getting state definition by name",
                exc_info=True,
            )
            return None

    async def update(
        self, state_definition_id: uuid.UUID, **kwargs: object
    ) -> VisionEntityStateDefinitionData | None:
        try:
            result = await self.session.execute(
                select(VisionEntityStateDefinition).filter(
                    VisionEntityStateDefinition.id == state_definition_id
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
                "[Vision Entity] DB error updating state definition", exc_info=True
            )
            raise

    async def delete(self, state_definition_id: uuid.UUID) -> bool:
        try:
            result = await self.session.execute(
                select(VisionEntityStateDefinition).filter(
                    VisionEntityStateDefinition.id == state_definition_id
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
                "[Vision Entity] DB error deleting state definition", exc_info=True
            )
            raise

    async def delete_by_entity_type(self, entity_type_id: uuid.UUID) -> int:
        try:
            result = await self.session.execute(
                select(VisionEntityStateDefinition).filter(
                    VisionEntityStateDefinition.entity_type_id == entity_type_id
                )
            )
            rows = result.scalars().all()
            for row in rows:
                await self.session.delete(row)
            await self.session.commit()
            return len(rows)
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error deleting state definitions for entity type",
                exc_info=True,
            )
            raise

    async def count_entities_using_state(self, state_definition_id: uuid.UUID) -> int:
        from db.tables import VisionEntity

        try:
            result = await self.session.execute(
                select(VisionEntity.id).filter(
                    VisionEntity.current_state_id == state_definition_id
                )
            )
            return len(result.all())
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error counting entities using state",
                exc_info=True,
            )
            raise

    async def delete_if_unused(self, state_definition_id: uuid.UUID) -> bool:
        from db.tables import VisionEntity

        try:
            result = await self.session.execute(
                select(VisionEntity.id)
                .filter(VisionEntity.current_state_id == state_definition_id)
                .limit(1)
            )
            if result.first() is not None:
                return False

            del_result = await self.session.execute(
                delete(VisionEntityStateDefinition).filter(
                    VisionEntityStateDefinition.id == state_definition_id
                )
            )
            await self.session.commit()
            return del_result.rowcount > 0  # type: ignore[union-attr]
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error in guarded state definition delete",
                exc_info=True,
            )
            raise

    async def clear_default_for_entity_type(self, entity_type_id: uuid.UUID) -> None:
        try:
            result = await self.session.execute(
                select(VisionEntityStateDefinition).filter(
                    VisionEntityStateDefinition.entity_type_id == entity_type_id,
                    VisionEntityStateDefinition.is_default.is_(True),
                )
            )
            for row in result.scalars().all():
                row.is_default = False
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error clearing defaults for entity type",
                exc_info=True,
            )
            raise
