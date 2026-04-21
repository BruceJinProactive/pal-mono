from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.pal_repository.data_classes.agent import AgentData
from db.tables.agents import Agent
from utils.log import logger

_MUTABLE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "communication_style",
        "interaction_guidelines",
        "agent_type",
        "voice_id",
        "cloned_voice_id",
        "has_voice_clone",
        "greeting_message",
        "speech_rate",
        "background_noise",
        "memory_enabled",
        "language",
        "filler_words",
        "raw_config",
    }
)


def _to_data(row: Agent) -> AgentData:
    """Convert an ORM Agent to an AgentData."""
    return AgentData(
        id=row.id,
        account_id=row.account_id,
        name=row.name or "",
        agent_type=row.agent_type.value if row.agent_type else "",
        speech_rate=row.speech_rate.value if row.speech_rate else "",
        language=row.language.value if row.language else "",
        has_voice_clone=row.has_voice_clone or False,
        background_noise=row.background_noise or False,
        memory_enabled=row.memory_enabled or False,
        created_at=row.created_at,
        description=row.description,
        communication_style=row.communication_style,
        interaction_guidelines=row.interaction_guidelines,
        voice_id=row.voice_id,
        cloned_voice_id=row.cloned_voice_id,
        greeting_message=row.greeting_message,
        filler_words=dict(row.filler_words) if row.filler_words else {},
        raw_config=dict(row.raw_config) if row.raw_config else {},
        updated_at=row.updated_at,
    )


class AgentRepository:
    """Async-only repository for Agent records.

    All methods return ``AgentData`` — ORM objects never escape
    this layer.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, agent_id: uuid.UUID) -> AgentData | None:
        """Retrieve a single agent by its primary key."""
        try:
            result = await self.session.execute(
                select(Agent)
                .options(selectinload(Agent.account))
                .where(Agent.id == agent_id)
            )
            row = result.scalars().first()
            return _to_data(row) if row else None
        except Exception:
            logger.exception("Error retrieving agent by ID")
            raise

    async def list_agents(self, skip: int = 0, limit: int = 100) -> list[AgentData]:
        """Retrieve a paginated list of agents."""
        try:
            result = await self.session.execute(select(Agent).offset(skip).limit(limit))
            rows = result.scalars().all()
            return [_to_data(row) for row in rows]
        except Exception:
            logger.exception("Error listing agents")
            raise

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create(self, account_id: uuid.UUID, **kwargs: object) -> AgentData:
        """Create a new agent.

        Raises:
            Exception: If the insert fails.
        """
        try:
            row = Agent(id=uuid.uuid4(), account_id=account_id)
            for key, value in kwargs.items():
                if value is not None and key in _MUTABLE_FIELDS:
                    setattr(row, key, value)
            self.session.add(row)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error creating agent")
            raise

    async def update(self, agent_id: uuid.UUID, **kwargs: object) -> AgentData | None:
        """Update an agent's fields. Returns None if not found."""
        try:
            result = await self.session.execute(
                select(Agent).filter(Agent.id == agent_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            for key, value in kwargs.items():
                if value is not None and key in _MUTABLE_FIELDS:
                    setattr(row, key, value)
            await self.session.commit()
            await self.session.refresh(row)
            return _to_data(row)
        except Exception:
            await self.session.rollback()
            logger.exception("Error updating agent")
            raise

    async def delete(self, agent_id: uuid.UUID) -> None:
        """Delete an agent by ID. No-op if not found."""
        try:
            result = await self.session.execute(
                select(Agent).filter(Agent.id == agent_id)
            )
            row = result.scalar_one_or_none()
            if row:
                await self.session.delete(row)
                await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.exception("Error deleting agent")
            raise
