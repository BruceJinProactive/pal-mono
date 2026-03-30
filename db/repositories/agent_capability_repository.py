"""Agent Capability Repository.

Provides async database operations for agent capability management.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import AgentCapability
from utils.log import logger


class AgentCapabilityRepositoryAsync:
    """Async repository for agent capability operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, capability: AgentCapability) -> AgentCapability:
        """
        Create a new agent capability.

        Args:
            capability: AgentCapability object to create.

        Returns:
            The created AgentCapability object.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            self.session.add(capability)
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(capability)
            return capability
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating agent capability: {e}")
            raise

    async def get_by_id(self, capability_id: uuid.UUID) -> Optional[AgentCapability]:
        """
        Retrieve an agent capability by ID.

        Args:
            capability_id: UUID of the agent capability.

        Returns:
            AgentCapability if found, None otherwise.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        query = select(AgentCapability).filter(AgentCapability.id == capability_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_agent_and_capability(
        self, agent_id: uuid.UUID, capability_identifier: str
    ) -> Optional[AgentCapability]:
        """
        Retrieve an agent capability by agent ID and capability identifier.

        Args:
            agent_id: UUID of the agent.
            capability_identifier: Identifier of the capability.

        Returns:
            AgentCapability if found, None otherwise.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        query = select(AgentCapability).filter(
            and_(
                AgentCapability.agent_id == agent_id,
                AgentCapability.capability_identifier == capability_identifier,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_agent(
        self, agent_id: uuid.UUID, enabled_only: bool = False
    ) -> list[AgentCapability]:
        """
        Get all capabilities for an agent.

        Args:
            agent_id: UUID of the agent.
            enabled_only: If True, only return enabled capabilities.

        Returns:
            List of AgentCapability objects, ordered by priority.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        query = select(AgentCapability).filter(AgentCapability.agent_id == agent_id)

        if enabled_only:
            query = query.filter(AgentCapability.enabled)

        query = query.order_by(AgentCapability.priority)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(
        self, capability_id: uuid.UUID, **kwargs
    ) -> Optional[AgentCapability]:
        """
        Update an agent capability.

        Args:
            capability_id: UUID of the agent capability to update.
            **kwargs: Fields to update.

        Returns:
            Updated AgentCapability if found, None otherwise.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            capability = await self.get_by_id(capability_id)
            if not capability:
                return None

            for key, value in kwargs.items():
                if hasattr(capability, key):
                    setattr(capability, key, value)

            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(capability)
            return capability
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating agent capability: {e}")
            raise

    async def delete(self, capability_id: uuid.UUID) -> bool:
        """
        Delete an agent capability.

        Args:
            capability_id: UUID of the agent capability to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            capability = await self.get_by_id(capability_id)
            if not capability:
                return False

            await self.session.delete(capability)
            await self.session.flush()
            await self.session.commit()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting agent capability: {e}")
            raise

    async def upsert(
        self,
        agent_id: uuid.UUID,
        capability_identifier: str,
        priority: int = 50,
        enabled: bool = True,
    ) -> AgentCapability:
        """
        Create or update an agent capability.

        Args:
            agent_id: UUID of the agent.
            capability_identifier: Identifier of the capability.
            priority: Position in prompt (higher number = later = stronger via recency).
            enabled: Whether the capability is enabled.

        Returns:
            The created or updated AgentCapability object.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            # Check if the capability already exists
            existing = await self.get_by_agent_and_capability(
                agent_id, capability_identifier
            )

            if existing:
                # Update existing capability
                existing.priority = priority
                existing.enabled = enabled
                await self.session.flush()
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            else:
                # Create new capability
                capability = AgentCapability(
                    id=uuid.uuid4(),
                    agent_id=agent_id,
                    capability_identifier=capability_identifier,
                    priority=priority,
                    enabled=enabled,
                )
                return await self.create(capability)
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error upserting agent capability: {e}")
            raise

    async def bulk_update_priorities(
        self, capability_updates: list[tuple[uuid.UUID, int]]
    ) -> tuple[int, int]:
        """
        Bulk update priorities for multiple capabilities.

        Args:
            capability_updates: List of tuples (capability_id, new_priority).

        Returns:
            Tuple of (updated_count, requested_count).
            - updated_count: Number of capabilities actually updated
            - requested_count: Total number of updates requested
            Caller can decide if partial success is acceptable.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            updated_count = 0
            for capability_id, new_priority in capability_updates:
                capability = await self.get_by_id(capability_id)
                if capability:
                    capability.priority = new_priority
                    updated_count += 1

            await self.session.flush()
            await self.session.commit()
            return (updated_count, len(capability_updates))
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error bulk updating capability priorities: {e}")
            raise
