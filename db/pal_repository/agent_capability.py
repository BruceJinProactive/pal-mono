from __future__ import annotations

import uuid

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.pal_repository.data_classes.agent_capability import AgentCapabilityData
from db.tables.agent_capabilities import AgentCapability
from utils.log import logger


def _to_data(row: AgentCapability) -> AgentCapabilityData:
    """Convert an ORM AgentCapability to an AgentCapabilityData."""
    return AgentCapabilityData(
        id=row.id,
        agent_id=row.agent_id,
        capability_identifier=row.capability_identifier,
        priority=row.priority,
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class AgentCapabilityRepository:
    """Async-only repository for AgentCapability records.

    All methods return ``AgentCapabilityData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, capability_id: uuid.UUID) -> AgentCapabilityData | None:
        """Retrieve an agent capability by ID."""
        try:
            result = await self.session.execute(
                select(AgentCapability).filter(AgentCapability.id == capability_id)
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving agent capability by ID")
            raise

    async def get_by_agent_and_capability(
        self, agent_id: uuid.UUID, capability_identifier: str
    ) -> AgentCapabilityData | None:
        """Retrieve by agent ID and capability identifier."""
        try:
            result = await self.session.execute(
                select(AgentCapability).filter(
                    and_(
                        AgentCapability.agent_id == agent_id,
                        AgentCapability.capability_identifier == capability_identifier,
                    )
                )
            )
            row = result.scalar_one_or_none()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving agent capability")
            raise

    async def get_by_agent(
        self, agent_id: uuid.UUID, enabled_only: bool = False
    ) -> list[AgentCapabilityData]:
        """Get all capabilities for an agent, ordered by priority."""
        try:
            query = select(AgentCapability).filter(AgentCapability.agent_id == agent_id)
            if enabled_only:
                query = query.filter(AgentCapability.enabled.is_(True))
            query = query.order_by(AgentCapability.priority)
            result = await self.session.execute(query)
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing agent capabilities")
            raise

    async def upsert(
        self,
        agent_id: uuid.UUID,
        capability_identifier: str,
        priority: int = 50,
        enabled: bool = True,
    ) -> AgentCapabilityData:
        """Create or update an agent capability.

        Uses an atomic INSERT … ON CONFLICT DO UPDATE keyed on
        ``uq_agent_capability(agent_id, capability_identifier)`` so concurrent
        calls cannot create duplicate rows.
        """
        try:
            stmt = pg_insert(AgentCapability).values(
                id=uuid.uuid4(),
                agent_id=agent_id,
                capability_identifier=capability_identifier,
                priority=priority,
                enabled=enabled,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_agent_capability",
                set_={"priority": priority, "enabled": enabled},
            ).returning(AgentCapability)
            result = await self.session.execute(stmt)
            row = result.scalar_one()
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error upserting agent capability")
            raise

    async def delete(self, capability_id: uuid.UUID) -> bool:
        """Delete an agent capability. Returns True if deleted."""
        try:
            result = await self.session.execute(
                select(AgentCapability).filter(AgentCapability.id == capability_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return False
            await self.session.delete(row)
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            logger.exception("Error deleting agent capability")
            raise
