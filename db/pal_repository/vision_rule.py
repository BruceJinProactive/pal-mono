from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.vision_rule import VisionRuleData
from db.tables import Project, VisionRule
from utils.log import logger


def _to_data(row: VisionRule) -> VisionRuleData:
    return VisionRuleData(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        type=row.type.value if row.type else "",
        severity=row.severity,
        is_active=row.is_active,
        rule_metadata=dict(row.rule_metadata) if row.rule_metadata else {},
        description=row.description,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class VisionRuleRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: VisionRuleData) -> None:
        try:
            row = VisionRule(
                id=record.id,
                project_id=record.project_id,
                name=record.name,
                type=record.type,
                severity=record.severity,
                is_active=record.is_active,
                rule_metadata=record.rule_metadata,
                description=record.description,
            )
            self.session.add(row)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Rule] DB error creating rule", exc_info=True)
            raise

    async def get_by_id(self, rule_id: uuid.UUID) -> VisionRuleData | None:
        try:
            result = await self.session.execute(
                select(VisionRule).filter(VisionRule.id == rule_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Rule] DB error getting rule by id", exc_info=True)
            return None

    async def get_by_id_for_account(
        self, rule_id: uuid.UUID, account_id: uuid.UUID
    ) -> VisionRuleData | None:
        try:
            result = await self.session.execute(
                select(VisionRule)
                .join(Project, VisionRule.project_id == Project.id)
                .filter(
                    VisionRule.id == rule_id,
                    Project.account_id == account_id,
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Rule] DB error getting rule by id for account", exc_info=True
            )
            return None

    async def list_by_account(
        self,
        account_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        limit: int = 100,
    ) -> list[VisionRuleData]:
        try:
            query = (
                select(VisionRule)
                .join(Project, VisionRule.project_id == Project.id)
                .filter(Project.account_id == account_id)
            )
            if project_id is not None:
                query = query.filter(VisionRule.project_id == project_id)
            if is_active is not None:
                query = query.filter(VisionRule.is_active == is_active)
            query = query.order_by(VisionRule.created_at.desc()).limit(limit)
            result = await self.session.execute(query)
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Rule] DB error listing rules", exc_info=True)
            return []

    async def update(self, rule_id: uuid.UUID, **kwargs: Any) -> VisionRuleData | None:
        try:
            await self.session.execute(
                update(VisionRule).where(VisionRule.id == rule_id).values(**kwargs)
            )
            await self.session.commit()
            return await self.get_by_id(rule_id)
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Rule] DB error updating rule", exc_info=True)
            raise

    async def delete_for_account(
        self, rule_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        try:
            subquery = (
                select(VisionRule.id)
                .join(Project, VisionRule.project_id == Project.id)
                .filter(
                    VisionRule.id == rule_id,
                    Project.account_id == account_id,
                )
            )
            result = await self.session.execute(
                delete(VisionRule).where(VisionRule.id.in_(subquery))
            )
            await self.session.commit()
            return (result.rowcount or 0) > 0
        except Exception:
            await self.session.rollback()
            logger.error("[Vision Rule] DB error deleting rule", exc_info=True)
            raise

    async def verify_project_belongs_to_account(
        self, project_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        try:
            result = await self.session.execute(
                select(Project.id).filter(
                    Project.id == project_id,
                    Project.account_id == account_id,
                )
            )
            return result.scalar_one_or_none() is not None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision Rule] DB error verifying project ownership", exc_info=True
            )
            return False
