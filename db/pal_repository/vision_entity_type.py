from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.vision_entity_type import VisionEntityTypeData
from db.tables import VisionEntityType
from utils.log import logger


def _to_data(row: VisionEntityType) -> VisionEntityTypeData:
    return VisionEntityTypeData(
        id=row.id,
        account_id=row.account_id,
        name=row.name,
        display_name=row.display_name,
        description=row.description,
        icon=row.icon,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class VisionEntityTypeRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: VisionEntityTypeData) -> None:
        try:
            row = VisionEntityType(
                id=record.id,
                account_id=record.account_id,
                name=record.name,
                display_name=record.display_name,
                description=record.description,
                icon=record.icon,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Entity] DB error creating entity type", exc_info=True)
            raise

    async def get_by_id(self, entity_type_id: uuid.UUID) -> VisionEntityTypeData | None:
        try:
            result = await self.session.execute(
                select(VisionEntityType).filter(VisionEntityType.id == entity_type_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error getting entity type by id", exc_info=True
            )
            return None

    async def get_by_account(
        self,
        account_id: uuid.UUID,
        is_active: bool | None = None,
    ) -> list[VisionEntityTypeData]:
        try:
            query = select(VisionEntityType).filter(
                VisionEntityType.account_id == account_id
            )
            if is_active is not None:
                query = query.filter(VisionEntityType.is_active == is_active)
            query = query.order_by(VisionEntityType.created_at)
            result = await self.session.execute(query)
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error listing entity types by account",
                exc_info=True,
            )
            return []

    async def get_by_account_and_name(
        self,
        account_id: uuid.UUID,
        name: str,
    ) -> VisionEntityTypeData | None:
        try:
            result = await self.session.execute(
                select(VisionEntityType).filter(
                    VisionEntityType.account_id == account_id,
                    VisionEntityType.name == name,
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Entity] DB error getting entity type by name", exc_info=True
            )
            return None

    async def update(
        self, entity_type_id: uuid.UUID, **kwargs: object
    ) -> VisionEntityTypeData | None:
        try:
            result = await self.session.execute(
                select(VisionEntityType).filter(VisionEntityType.id == entity_type_id)
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
            logger.error("[Vision Entity] DB error updating entity type", exc_info=True)
            raise

    async def delete(self, entity_type_id: uuid.UUID) -> bool:
        try:
            result = await self.session.execute(
                select(VisionEntityType).filter(VisionEntityType.id == entity_type_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return False

            await self.session.delete(row)
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Entity] DB error deleting entity type", exc_info=True)
            raise
