"""
Implementation of capability service business logic
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

import db
from db.tables import AgentCapability, CapabilityAction
from db.tables.change_log import ChangeResourceType
from services.history_service._implementation import create_change_log
from services.prompt_service.prompts_v2 import PromptFactoryV2
from utils.log import logger

from .schema import (
    ActionCreate,
    ActionResponse,
    ActionUpdate,
    AgentCapabilityCreate,
    AgentCapabilityResponse,
    AgentCapabilityUpdate,
    BulkPriorityUpdate,
    BulkPriorityUpdateResponse,
    CapabilityWithActions,
    DefaultAction,
    DefaultCapabilitiesResponse,
    DefaultCapability,
)

# ============= Default Capabilities Functions =============


def get_default_capabilities() -> DefaultCapabilitiesResponse:
    """
    Get all available default capabilities from YAML configuration.

    This returns the list of valid capability identifiers that can be used
    when creating agent capabilities. These are loaded from the YAML files
    in the prompt system.

    Returns:
        List of all default capabilities with their metadata and action instructions
    """
    # Ensure PromptFactoryV2 is initialized by creating an instance
    # This will load the YAML files if not already loaded
    _ = PromptFactoryV2()

    # Get default capabilities from the class variable
    default_capabilities = PromptFactoryV2._default_capabilities

    capabilities = []
    for identifier, capability in default_capabilities.items():
        # Create description based on identifier
        descriptions = {
            "general": "General store information and FAQs",
            "ordering": "Food ordering and order management",
            "reservation": "Table reservation management",
            "waitlist": "Waitlist and queue management",
        }

        # Build list of actions with their full instructions
        actions = []
        for action in capability.actions:
            actions.append(
                DefaultAction(
                    action=action.action,
                    instruction=action.instruction,
                    priority=action.priority,
                    channels=str(action.channel),  # Convert to string representation
                )
            )

        # Sort actions by priority for consistent ordering
        actions.sort(key=lambda a: a.priority)

        capabilities.append(
            DefaultCapability(
                identifier=identifier,
                priority=capability.priority,
                enabled=capability.enabled,
                description=descriptions.get(
                    identifier, f"{identifier.replace('_', ' ').title()} capability"
                ),
                actions=actions,
            )
        )

    # Sort by priority for consistent ordering
    capabilities.sort(key=lambda c: c.priority)

    return DefaultCapabilitiesResponse(capabilities=capabilities)


# ============= Agent Capability Functions =============


async def create_agent_capability(
    session: AsyncSession,
    agent_id: UUID,
    data: AgentCapabilityCreate,
) -> AgentCapabilityResponse:
    """
    Create a new agent capability configuration.

    Args:
        session: Database session
        agent_id: Agent ID
        data: Capability creation data

    Returns:
        Created agent capability

    Raises:
        ValueError: If capability already exists for this agent
    """
    repo = db.AgentCapabilityRepositoryAsync(session)

    # Check if capability already exists
    existing = await repo.get_by_agent_and_capability(
        agent_id, data.capability_identifier
    )
    if existing:
        raise ValueError(
            f"Capability '{data.capability_identifier}' already exists for this agent"
        )

    # Create new capability object
    new_capability = AgentCapability(
        agent_id=agent_id,
        capability_identifier=data.capability_identifier,
        priority=data.priority,
        enabled=data.enabled,
    )

    # Save to database
    capability = await repo.create(new_capability)

    if not capability:
        raise ValueError("Failed to create agent capability")

    logger.info(
        f"Created capability '{data.capability_identifier}' for agent {agent_id}"
    )
    return AgentCapabilityResponse.model_validate(capability)


async def get_agent_capabilities(
    session: AsyncSession,
    agent_id: UUID,
    enabled_only: bool = False,
) -> list[AgentCapabilityResponse]:
    """
    Get all capabilities for an agent.

    Args:
        session: Database session
        agent_id: Agent ID
        enabled_only: Whether to return only enabled capabilities

    Returns:
        List of agent capabilities
    """
    repo = db.AgentCapabilityRepositoryAsync(session)
    capabilities = await repo.get_by_agent(agent_id, enabled_only)

    return [AgentCapabilityResponse.model_validate(cap) for cap in capabilities]


async def update_agent_capability(
    session: AsyncSession,
    capability_id: UUID,
    data: AgentCapabilityUpdate,
) -> Optional[AgentCapabilityResponse]:
    """
    Update an agent capability.

    Args:
        session: Database session
        capability_id: Capability ID
        data: Update data

    Returns:
        Updated capability if found, None otherwise
    """
    repo = db.AgentCapabilityRepositoryAsync(session)

    # Build update dict with only provided fields
    update_data = {}
    if data.priority is not None:
        update_data["priority"] = data.priority
    if data.enabled is not None:
        update_data["enabled"] = data.enabled

    if not update_data:
        # No fields to update
        capability = await repo.get_by_id(capability_id)
        if capability:
            return AgentCapabilityResponse.model_validate(capability)
        return None

    capability = await repo.update(capability_id, **update_data)

    if capability:
        logger.info(f"Updated capability {capability_id}")
        return AgentCapabilityResponse.model_validate(capability)
    return None


async def delete_agent_capability(
    session: AsyncSession,
    capability_id: UUID,
) -> bool:
    """
    Delete an agent capability and all its actions.

    Args:
        session: Database session
        capability_id: Capability ID

    Returns:
        True if deleted, False if not found
    """
    cap_repo = db.AgentCapabilityRepositoryAsync(session)
    action_repo = db.CapabilityActionRepositoryAsync(session)

    # Delete all actions for this capability first
    await action_repo.bulk_delete_by_capability(capability_id)

    # Delete the capability
    deleted = await cap_repo.delete(capability_id)

    if deleted:
        logger.info(f"Deleted capability {capability_id} and its actions")
    return deleted


async def bulk_update_priorities(
    session: AsyncSession,
    data: BulkPriorityUpdate,
) -> BulkPriorityUpdateResponse:
    """
    Bulk update priorities for multiple capabilities.

    Args:
        session: Database session
        data: Bulk update data

    Returns:
        Update response with counts
    """
    repo = db.AgentCapabilityRepositoryAsync(session)
    updated_count, requested_count = await repo.bulk_update_priorities(data.updates)

    return BulkPriorityUpdateResponse(
        updated_count=updated_count,
        requested_count=requested_count,
        success=(updated_count == requested_count),
    )


# ============= Capability Action Functions =============


async def create_capability_action(
    session: AsyncSession,
    data: ActionCreate,
    author: str,
) -> ActionResponse:
    """
    Create a new capability action.

    Args:
        session: Database session
        data: Action creation data
        author: Email of the user making the change

    Returns:
        Created action

    Raises:
        ValueError: If action already exists or capability not found
    """
    # Verify capability exists
    cap_repo = db.AgentCapabilityRepositoryAsync(session)
    capability = await cap_repo.get_by_id(data.agent_capability_id)
    if not capability:
        raise ValueError(f"Agent capability {data.agent_capability_id} not found")

    # Get agent to find account_id for change tracking
    agent_repo = db.AgentRepositoryAsync(session)
    agent = await agent_repo.get_agent(capability.agent_id)
    if not agent:
        raise ValueError(f"Agent {capability.agent_id} not found")

    # Check if action already exists
    action_repo = db.CapabilityActionRepositoryAsync(session)
    existing_action = await action_repo.get_by_capability_and_action(
        agent_capability_id=data.agent_capability_id,
        action=data.action,
        channel=data.channel.upper(),  # Normalize to uppercase
    )
    if existing_action:
        raise ValueError(
            f"Action '{data.action}' already exists for capability {data.agent_capability_id} "
            f"with channel {data.channel.upper()}"
        )

    # Create the action
    new_action = CapabilityAction(
        agent_capability_id=data.agent_capability_id,
        action=data.action,
        prompt=data.prompt,
        channel=data.channel.upper(),  # Normalize to uppercase
        priority=data.priority,
        enabled=data.enabled,
    )

    action = await action_repo.create(new_action)

    if not action:
        raise ValueError("Failed to create capability action")

    # Create change log entry
    await session.run_sync(
        lambda sync_session: create_change_log(
            session=sync_session,
            account_id=agent.account_id,
            resource_type=ChangeResourceType.CapabilityAction,
            resource_id=str(action.id),
            author=author,
            old_record=None,
            new_record=action,
        )
    )

    logger.info(
        f"Created action '{data.action}' for capability {data.agent_capability_id}"
    )
    return ActionResponse.model_validate(action)


async def get_capability_actions(
    session: AsyncSession,
    capability_id: UUID,
    channel: Optional[str] = None,
) -> list[ActionResponse]:
    """
    Get actions for a capability.

    Args:
        session: Database session
        capability_id: Capability ID
        channel: Optional channel filter

    Returns:
        List of actions
    """
    action_repo = db.CapabilityActionRepositoryAsync(session)
    actions = await action_repo.get_by_capability(capability_id, channel)

    return [ActionResponse.model_validate(action) for action in actions]


async def update_capability_action(
    session: AsyncSession,
    action_id: UUID,
    data: ActionUpdate,
    author: str,
) -> Optional[ActionResponse]:
    """
    Update a capability action.

    Args:
        session: Database session
        action_id: Action ID
        data: Update data
        author: Email of the user making the change

    Returns:
        Updated action if found, None otherwise
    """
    action_repo = db.CapabilityActionRepositoryAsync(session)
    cap_repo = db.AgentCapabilityRepositoryAsync(session)
    agent_repo = db.AgentRepositoryAsync(session)

    # Get the old action record for change tracking
    old_action = await action_repo.get_by_id(action_id)
    if not old_action:
        return None

    # Build update dict
    update_data = {}
    if data.prompt is not None:
        update_data["prompt"] = data.prompt
    if data.channel is not None:
        update_data["channel"] = data.channel.upper()
    if data.priority is not None:
        update_data["priority"] = data.priority
    if data.enabled is not None:
        update_data["enabled"] = data.enabled

    if not update_data:
        # No fields to update
        return ActionResponse.model_validate(old_action)

    # Get capability and agent to find account_id for change tracking
    capability = await cap_repo.get_by_id(old_action.agent_capability_id)
    if not capability:
        return None

    agent = await agent_repo.get_agent(capability.agent_id)
    if not agent:
        return None

    # Update the action
    action = await action_repo.update(action_id, **update_data)
    if not action:
        return None

    # Create change log entry
    await session.run_sync(
        lambda sync_session: create_change_log(
            session=sync_session,
            account_id=agent.account_id,
            resource_type=ChangeResourceType.CapabilityAction,
            resource_id=str(action_id),
            author=author,
            old_record=old_action,
            new_record=action,
        )
    )

    logger.info(f"Updated action {action_id}")
    return ActionResponse.model_validate(action)


async def upsert_capability_action(
    session: AsyncSession,
    data: ActionCreate,
) -> ActionResponse:
    """
    Create or update a capability action.

    If an action with the same agent_capability_id, action name, and channel
    already exists, it will be updated. Otherwise, a new action will be created.

    Args:
        session: Database session
        data: Action creation/update data

    Returns:
        Created or updated action

    Raises:
        ValueError: If capability not found
    """
    # Verify capability exists
    cap_repo = db.AgentCapabilityRepositoryAsync(session)
    capability = await cap_repo.get_by_id(data.agent_capability_id)
    if not capability:
        raise ValueError(f"Agent capability {data.agent_capability_id} not found")

    # Upsert the action
    action_repo = db.CapabilityActionRepositoryAsync(session)
    action = await action_repo.upsert(
        agent_capability_id=data.agent_capability_id,
        action=data.action,
        prompt=data.prompt,
        channel=data.channel.upper(),  # Normalize to uppercase
        priority=data.priority,
        enabled=data.enabled,
    )

    if not action:
        raise ValueError("Failed to upsert capability action")

    logger.info(
        f"Upserted action '{data.action}' for capability {data.agent_capability_id}"
    )
    return ActionResponse.model_validate(action)


async def delete_capability_action(
    session: AsyncSession,
    action_id: UUID,
    author: str,
) -> bool:
    """
    Delete a capability action.

    Args:
        session: Database session
        action_id: Action ID
        author: Email of the user making the change

    Returns:
        True if deleted, False if not found
    """
    action_repo = db.CapabilityActionRepositoryAsync(session)
    cap_repo = db.AgentCapabilityRepositoryAsync(session)
    agent_repo = db.AgentRepositoryAsync(session)

    # Get the action record before deletion for change tracking
    old_action = await action_repo.get_by_id(action_id)
    if not old_action:
        return False

    # Get capability and agent to find account_id for change tracking
    capability = await cap_repo.get_by_id(old_action.agent_capability_id)
    if not capability:
        return False

    agent = await agent_repo.get_agent(capability.agent_id)
    if not agent:
        return False

    # Delete the action
    deleted = await action_repo.delete(action_id)
    if not deleted:
        return False

    # Create change log entry
    await session.run_sync(
        lambda sync_session: create_change_log(
            session=sync_session,
            account_id=agent.account_id,
            resource_type=ChangeResourceType.CapabilityAction,
            resource_id=str(action_id),
            author=author,
            old_record=old_action,
            new_record=None,
        )
    )

    logger.info(f"Deleted action {action_id}")
    return deleted


# ============= Combined Functions =============


async def get_agent_capabilities_with_actions(
    session: AsyncSession,
    agent_id: UUID,
    channel: Optional[str] = None,
    enabled_only: bool = False,
) -> list[CapabilityWithActions]:
    """
    Get all capabilities for an agent with their actions.

    Args:
        session: Database session
        agent_id: Agent ID
        channel: Optional channel filter for actions
        enabled_only: Whether to return only enabled capabilities

    Returns:
        List of capabilities with their actions
    """
    # Get capabilities
    cap_repo = db.AgentCapabilityRepositoryAsync(session)
    capabilities = await cap_repo.get_by_agent(agent_id, enabled_only)

    if not capabilities:
        return []

    # Get actions for all capabilities
    capability_ids = [cap.id for cap in capabilities]
    action_repo = db.CapabilityActionRepositoryAsync(session)
    actions_by_capability = await action_repo.get_actions_for_capabilities(
        capability_ids, channel
    )

    # Build response
    result = []
    for cap in capabilities:
        cap_with_actions = CapabilityWithActions.model_validate(cap)
        if cap.id in actions_by_capability:
            cap_with_actions.actions = [
                ActionResponse.model_validate(action)
                for action in actions_by_capability[cap.id]
            ]
        result.append(cap_with_actions)

    return result
