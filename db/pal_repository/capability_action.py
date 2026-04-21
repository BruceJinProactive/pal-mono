from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.capability_action import CapabilityActionData
from db.tables.capability_actions import CapabilityAction
from utils.log import logger


def _to_data(row: CapabilityAction) -> CapabilityActionData:
    """Convert an ORM CapabilityAction to a CapabilityActionData."""
    return CapabilityActionData(
        id=row.id,
        agent_capability_id=row.agent_capability_id,
        action=row.action,
        prompt=row.prompt,
        channel=row.channel,
        priority=row.priority,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class CapabilityActionRepository:
    """Async-only repository for CapabilityAction records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, action_id: uuid.UUID) -> CapabilityActionData | None:
        """Retrieve a capability action by ID."""
        try:
            result = await self.session.execute(
                select(CapabilityAction).filter(CapabilityAction.id == action_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving capability action by ID")
            raise

    async def get_by_capability(
        self, agent_capability_id: uuid.UUID, channel: str | None = None
    ) -> list[CapabilityActionData]:
        """Get all actions for an agent capability, ordered by priority."""
        try:
            query = select(CapabilityAction).filter(
                CapabilityAction.agent_capability_id == agent_capability_id
            )
            if channel:
                normalized = channel.upper()
                query = query.filter(CapabilityAction.channel.in_([normalized, "ALL"]))
            query = query.order_by(CapabilityAction.priority)
            result = await self.session.execute(query)
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing capability actions")
            raise

    async def upsert(
        self,
        agent_capability_id: uuid.UUID,
        action: str,
        prompt: str,
        channel: str = "ALL",
        priority: int = 50,
        enabled: bool = False,
    ) -> CapabilityActionData:
        """Create or update a capability action.

        Uses an atomic INSERT ... ON CONFLICT DO UPDATE keyed on
        ``uq_capability_action_channel(agent_capability_id, action, channel)``
        so concurrent calls cannot create duplicate rows.
        """
        try:
            stmt = pg_insert(CapabilityAction).values(
                id=uuid.uuid4(),
                agent_capability_id=agent_capability_id,
                action=action,
                prompt=prompt,
                channel=channel,
                priority=priority,
                enabled=enabled,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_capability_action_channel",
                set_={"prompt": prompt, "priority": priority, "enabled": enabled},
            ).returning(CapabilityAction)
            result = await self.session.execute(stmt)
            row = result.scalar_one()
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error upserting capability action")
            raise

    async def delete(self, action_id: uuid.UUID) -> bool:
        """Delete a capability action. Returns True if deleted."""
        try:
            result = await self.session.execute(
                select(CapabilityAction).filter(CapabilityAction.id == action_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return False
            await self.session.delete(row)
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            logger.exception("Error deleting capability action")
            raise
