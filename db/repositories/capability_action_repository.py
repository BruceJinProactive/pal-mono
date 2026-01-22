"""Capability Action Repository.

Provides async database operations for capability action management.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.tables import CapabilityAction
from utils.log import logger


class CapabilityActionRepositoryAsync:
    """Async repository for capability action operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, action: CapabilityAction) -> CapabilityAction:
        """
        Create a new capability action.

        Args:
            action: CapabilityAction object to create.

        Returns:
            The created CapabilityAction object.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            self.session.add(action)
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(action)
            return action
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error creating capability action: {e}")
            raise

    async def get_by_id(self, action_id: uuid.UUID) -> Optional[CapabilityAction]:
        """
        Retrieve a capability action by ID.

        Args:
            action_id: UUID of the capability action.

        Returns:
            CapabilityAction if found, None otherwise.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        query = select(CapabilityAction).filter(CapabilityAction.id == action_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_capability_and_action(
        self,
        agent_capability_id: uuid.UUID,
        action: str,
        channel: str = "ALL",
    ) -> Optional[CapabilityAction]:
        """
        Retrieve a capability action by capability ID, action name, and channel.

        Args:
            agent_capability_id: UUID of the agent capability.
            action: Name of the action.
            channel: Channel for the action (default: "ALL").

        Returns:
            CapabilityAction if found, None otherwise.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        query = select(CapabilityAction).filter(
            and_(
                CapabilityAction.agent_capability_id == agent_capability_id,
                CapabilityAction.action == action,
                CapabilityAction.channel == channel,
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_capability(
        self,
        agent_capability_id: uuid.UUID,
        channel: Optional[str] = None,
    ) -> list[CapabilityAction]:
        """
        Get all actions for an agent capability.

        Args:
            agent_capability_id: UUID of the agent capability.
            channel: Optional channel filter. If provided, returns actions for
                    this channel and "ALL" channel.

        Returns:
            List of CapabilityAction objects, ordered by priority.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        query = select(CapabilityAction).filter(
            CapabilityAction.agent_capability_id == agent_capability_id
        )

        if channel:
            # Get actions for specific channel and "ALL" channel
            query = query.filter(CapabilityAction.channel.in_([channel, "ALL"]))

        query = query.order_by(CapabilityAction.priority)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_action_name(
        self,
        action: str,
        agent_capability_ids: Optional[list[uuid.UUID]] = None,
        channel: Optional[str] = None,
    ) -> list[CapabilityAction]:
        """
        Get all capability actions with a specific action name.

        Args:
            action: Name of the action.
            agent_capability_ids: Optional list of capability IDs to filter by.
            channel: Optional channel filter.

        Returns:
            List of CapabilityAction objects, ordered by priority.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        query = select(CapabilityAction).filter(CapabilityAction.action == action)

        if agent_capability_ids:
            query = query.filter(
                CapabilityAction.agent_capability_id.in_(agent_capability_ids)
            )

        if channel:
            query = query.filter(CapabilityAction.channel.in_([channel, "ALL"]))

        query = query.order_by(CapabilityAction.priority)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update(
        self, action_id: uuid.UUID, **kwargs
    ) -> Optional[CapabilityAction]:
        """
        Update a capability action.

        Args:
            action_id: UUID of the capability action to update.
            **kwargs: Fields to update.

        Returns:
            Updated CapabilityAction if found, None otherwise.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            action = await self.get_by_id(action_id)
            if not action:
                return None

            for key, value in kwargs.items():
                if hasattr(action, key):
                    setattr(action, key, value)

            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(action)
            return action
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error updating capability action: {e}")
            raise

    async def delete(self, action_id: uuid.UUID) -> bool:
        """
        Delete a capability action.

        Args:
            action_id: UUID of the capability action to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            action = await self.get_by_id(action_id)
            if not action:
                return False

            await self.session.delete(action)
            await self.session.flush()
            await self.session.commit()
            return True
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error deleting capability action: {e}")
            raise

    async def upsert(
        self,
        agent_capability_id: uuid.UUID,
        action: str,
        prompt: str,
        channel: str = "ALL",
        priority: int = 50,
        enabled: bool = False,
    ) -> CapabilityAction:
        """
        Create or update a capability action.

        Args:
            agent_capability_id: UUID of the agent capability.
            action: Name of the action.
            prompt: Prompt text for the action.
            channel: Channel for the action (default: "ALL").
            priority: Priority of the action (lower number = higher priority).
            enabled: Whether the action is enabled (default: False).

        Returns:
            The created or updated CapabilityAction object.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            # Check if the action already exists
            existing = await self.get_by_capability_and_action(
                agent_capability_id, action, channel
            )

            if existing:
                # Update existing action
                existing.prompt = prompt
                existing.priority = priority
                existing.enabled = enabled
                await self.session.flush()
                await self.session.commit()
                await self.session.refresh(existing)
                return existing
            else:
                # Create new action
                capability_action = CapabilityAction(
                    id=uuid.uuid4(),
                    agent_capability_id=agent_capability_id,
                    action=action,
                    prompt=prompt,
                    channel=channel,
                    priority=priority,
                    enabled=enabled,
                )
                return await self.create(capability_action)
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error upserting capability action: {e}")
            raise

    async def bulk_delete_by_capability(self, agent_capability_id: uuid.UUID) -> int:
        """
        Delete all actions for a capability.

        Args:
            agent_capability_id: UUID of the agent capability.

        Returns:
            Number of actions deleted.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        try:
            actions = await self.get_by_capability(agent_capability_id)
            count = len(actions)

            for action in actions:
                await self.session.delete(action)

            await self.session.flush()
            await self.session.commit()
            return count
        except SQLAlchemyError as e:
            await self.session.rollback()
            logger.error(f"Error bulk deleting capability actions: {e}")
            raise

    async def get_actions_for_capabilities(
        self,
        capability_ids: list[uuid.UUID],
        channel: Optional[str] = None,
    ) -> dict[uuid.UUID, list[CapabilityAction]]:
        """
        Get all actions for multiple capabilities, grouped by capability ID.

        Args:
            capability_ids: List of agent capability IDs.
            channel: Optional channel filter.

        Returns:
            Dictionary mapping capability IDs to lists of CapabilityAction objects,
            ordered by priority within each capability.

        Raises:
            SQLAlchemyError: If there is a database error.
        """
        query = select(CapabilityAction).filter(
            CapabilityAction.agent_capability_id.in_(capability_ids)
        )

        if channel:
            query = query.filter(CapabilityAction.channel.in_([channel, "ALL"]))

        query = query.order_by(
            CapabilityAction.agent_capability_id, CapabilityAction.priority
        )

        result = await self.session.execute(query)
        actions = result.scalars().all()

        # Group by capability ID
        capability_actions: dict[uuid.UUID, list[CapabilityAction]] = {}
        for action in actions:
            if action.agent_capability_id not in capability_actions:
                capability_actions[action.agent_capability_id] = []
            capability_actions[action.agent_capability_id].append(action)

        return capability_actions
