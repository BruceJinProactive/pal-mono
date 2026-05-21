from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.vision_rule_event import VisionRuleEventData
from db.tables import Project, VisionRule, VisionRuleEvent
from utils.log import logger


def _to_data(row: VisionRuleEvent) -> VisionRuleEventData:
    return VisionRuleEventData(
        id=row.id,
        rule_id=row.rule_id,
        entity_id=row.entity_id,
        state_change_event_id=row.state_change_event_id,
        severity=row.severity,
        triggered_at=row.triggered_at,
        event_metadata=dict(row.event_metadata) if row.event_metadata else {},
    )


class VisionRuleEventRepository:

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id_for_account(
        self, event_id: uuid.UUID, account_id: uuid.UUID
    ) -> VisionRuleEventData | None:
        try:
            result = await self.session.execute(
                select(VisionRuleEvent)
                .join(VisionRule, VisionRuleEvent.rule_id == VisionRule.id)
                .join(Project, VisionRule.project_id == Project.id)
                .filter(
                    VisionRuleEvent.id == event_id,
                    Project.account_id == account_id,
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            await self.session.rollback()
            logger.error(
                "[Vision RuleEvent] DB error getting event by id for account",
                exc_info=True,
            )
            return None

    async def list_by_account(
        self,
        account_id: uuid.UUID,
        rule_id: uuid.UUID | None = None,
        entity_id: uuid.UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
    ) -> list[VisionRuleEventData]:
        try:
            query = (
                select(VisionRuleEvent)
                .join(VisionRule, VisionRuleEvent.rule_id == VisionRule.id)
                .join(Project, VisionRule.project_id == Project.id)
                .filter(Project.account_id == account_id)
            )
            if rule_id is not None:
                query = query.filter(VisionRuleEvent.rule_id == rule_id)
            if entity_id is not None:
                query = query.filter(VisionRuleEvent.entity_id == entity_id)
            if start is not None:
                query = query.filter(VisionRuleEvent.triggered_at >= start)
            if end is not None:
                query = query.filter(VisionRuleEvent.triggered_at <= end)
            query = query.order_by(VisionRuleEvent.triggered_at.desc()).limit(limit)
            result = await self.session.execute(query)
            return [_to_data(row) for row in result.scalars().all()]
        except Exception:
            await self.session.rollback()
            logger.error("[Vision RuleEvent] DB error listing events", exc_info=True)
            return []

    async def delete_for_account(
        self, event_id: uuid.UUID, account_id: uuid.UUID
    ) -> bool:
        try:
            subquery = (
                select(VisionRuleEvent.id, VisionRuleEvent.triggered_at)
                .join(VisionRule, VisionRuleEvent.rule_id == VisionRule.id)
                .join(Project, VisionRule.project_id == Project.id)
                .filter(
                    VisionRuleEvent.id == event_id,
                    Project.account_id == account_id,
                )
            ).subquery()
            result = await self.session.execute(
                delete(VisionRuleEvent).where(
                    VisionRuleEvent.id == subquery.c.id,
                    VisionRuleEvent.triggered_at == subquery.c.triggered_at,
                )
            )
            await self.session.commit()
            return (result.rowcount or 0) > 0
        except Exception:
            await self.session.rollback()
            logger.error("[Vision RuleEvent] DB error deleting event", exc_info=True)
            raise
