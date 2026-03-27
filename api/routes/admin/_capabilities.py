"""
Implementation for managing agent capabilities and actions
"""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import services.capability_service as capability_service
from db.repositories.agent_capability_repository import AgentCapabilityRepositoryAsync
from db.repositories.capability_action_repository import CapabilityActionRepositoryAsync
from services.auth_types import UserContext
from services.capability_service.schema import (
    ActionCreate,
    ActionResponse,
    ActionUpdate,
    AgentCapabilityCreate,
    AgentCapabilityResponse,
    AgentCapabilityUpdate,
    BulkPriorityUpdate,
    BulkPriorityUpdateResponse,
    CapabilityWithActions,
    DefaultCapabilitiesResponse,
)

# ============= Default Capabilities Functions =============


def get_default_capabilities() -> DefaultCapabilitiesResponse:
    """
    Get all available default capabilities.

    Returns the list of valid capability identifiers that can be used
    when creating agent capabilities. These are the pre-defined capabilities
    from the system configuration.
    """
    return capability_service.get_default_capabilities()


# ============= Agent Capability Functions =============


async def create_agent_capability(
    agent_id: UUID,
    data: AgentCapabilityCreate,
    session: AsyncSession,
) -> AgentCapabilityResponse:
    """Create a new capability for an agent."""
    try:
        return await capability_service.create_agent_capability(session, agent_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        # Re-raise existing HTTPException
        raise


async def list_agent_capabilities(
    agent_id: UUID,
    enabled_only: bool,
    session: AsyncSession,
) -> list[AgentCapabilityResponse]:
    """List all capabilities for an agent."""
    return await capability_service.get_agent_capabilities(
        session, agent_id, enabled_only
    )


async def list_capabilities_with_actions(
    agent_id: UUID,
    channel: Optional[str],
    enabled_only: bool,
    session: AsyncSession,
) -> list[CapabilityWithActions]:
    """Get all capabilities with their actions for an agent."""
    return await capability_service.get_agent_capabilities_with_actions(
        session, agent_id, channel, enabled_only
    )


async def update_capability(
    agent_id: UUID,
    capability_id: UUID,
    data: AgentCapabilityUpdate,
    session: AsyncSession,
) -> AgentCapabilityResponse:
    """Update a capability."""
    # First, verify the capability belongs to the specified agent
    capability_repo = AgentCapabilityRepositoryAsync(session)
    capability = await capability_repo.get_by_id(capability_id)

    if not capability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {capability_id} not found",
        )

    if capability.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {capability_id} not found for agent {agent_id}",
        )

    # Update the capability
    updated_capability = await capability_service.update_agent_capability(
        session, capability_id, data
    )

    if not updated_capability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {capability_id} not found",
        )

    return updated_capability


async def delete_capability(
    agent_id: UUID,
    capability_id: UUID,
    session: AsyncSession,
) -> None:
    """Delete a capability and all its actions."""
    # First, verify the capability belongs to the specified agent
    capability_repo = AgentCapabilityRepositoryAsync(session)
    capability = await capability_repo.get_by_id(capability_id)

    if not capability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {capability_id} not found",
        )

    if capability.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {capability_id} not found for agent {agent_id}",
        )

    # Delete the capability
    deleted = await capability_service.delete_agent_capability(session, capability_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {capability_id} not found",
        )


async def bulk_update_priorities(
    agent_id: UUID,
    data: BulkPriorityUpdate,
    session: AsyncSession,
) -> BulkPriorityUpdateResponse:
    """Bulk update capability priorities for a single agent."""
    # Verify all capabilities belong to the specified agent
    capability_repo = AgentCapabilityRepositoryAsync(session)

    for capability_id, _ in data.updates:  # Unpack tuple (capability_id, new_priority)
        capability = await capability_repo.get_by_id(capability_id)
        if not capability:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Capability {capability_id} not found",
            )
        if capability.agent_id != agent_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Capability {capability_id} does not belong to agent {agent_id}",
            )

    # Update the priorities
    return await capability_service.bulk_update_priorities(session, data)


# ============= Capability Action Functions =============


async def create_action(
    agent_id: UUID,
    data: ActionCreate,
    context: UserContext,
    session: AsyncSession,
) -> ActionResponse:
    """Create a new capability action."""
    # Verify the capability belongs to the specified agent
    capability_repo = AgentCapabilityRepositoryAsync(session)
    capability = await capability_repo.get_by_id(data.agent_capability_id)

    if not capability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {data.agent_capability_id} not found",
        )

    if capability.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {data.agent_capability_id} not found for agent {agent_id}",
        )

    try:
        return await capability_service.create_capability_action(
            session, data, context.email
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        # Re-raise existing HTTPException
        raise


async def list_capability_actions(
    agent_id: UUID,
    capability_id: UUID,
    channel: Optional[str],
    session: AsyncSession,
) -> list[ActionResponse]:
    """List all actions for a capability."""
    # Verify the capability belongs to the specified agent
    capability_repo = AgentCapabilityRepositoryAsync(session)
    capability = await capability_repo.get_by_id(capability_id)

    if not capability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {capability_id} not found",
        )

    if capability.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {capability_id} not found for agent {agent_id}",
        )

    return await capability_service.get_capability_actions(
        session, capability_id, channel
    )


async def update_action(
    agent_id: UUID,
    action_id: UUID,
    data: ActionUpdate,
    context: UserContext,
    session: AsyncSession,
) -> ActionResponse:
    """Update a capability action."""
    # Get the action to find its capability
    action_repo = CapabilityActionRepositoryAsync(session)
    action = await action_repo.get_by_id(action_id)

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found",
        )

    # Get the capability to verify it belongs to the agent
    capability_repo = AgentCapabilityRepositoryAsync(session)
    capability = await capability_repo.get_by_id(action.agent_capability_id)

    if not capability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {action.agent_capability_id} not found",
        )

    if capability.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found for agent {agent_id}",
        )

    # Update the action
    updated_action = await capability_service.update_capability_action(
        session, action_id, data, context.email
    )
    if not updated_action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found",
        )
    return updated_action


async def delete_action(
    agent_id: UUID,
    action_id: UUID,
    context: UserContext,
    session: AsyncSession,
) -> None:
    """Delete a capability action."""
    # Get the action to find its capability
    action_repo = CapabilityActionRepositoryAsync(session)
    action = await action_repo.get_by_id(action_id)

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found",
        )

    # Get the capability to verify it belongs to the agent
    capability_repo = AgentCapabilityRepositoryAsync(session)
    capability = await capability_repo.get_by_id(action.agent_capability_id)

    if not capability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {action.agent_capability_id} not found",
        )

    if capability.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found for agent {agent_id}",
        )

    # Delete the action
    deleted = await capability_service.delete_capability_action(
        session, action_id, context.email
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found",
        )
