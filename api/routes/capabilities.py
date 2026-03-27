"""
API routes for managing agent capabilities and actions
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

import services.capability_service as capability_service
from db import get_db_async
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

router = APIRouter(prefix="/capabilities", tags=["Capabilities"])


# ============= Default Capabilities Endpoints =============


@router.get(
    "/defaults",
    response_model=DefaultCapabilitiesResponse,
    summary="Get default capabilities",
    description="Get all available default capability definitions from YAML configuration",
)
async def get_default_capabilities() -> DefaultCapabilitiesResponse:
    """
    Get all available default capabilities.

    Returns the list of valid capability identifiers that can be used
    when creating agent capabilities. These are the pre-defined capabilities
    from the system configuration.

    No authentication required as this is reference data.
    """
    return capability_service.get_default_capabilities()


# ============= Agent Capability Endpoints =============


@router.post(
    "/agents/{agent_id}/capabilities",
    response_model=AgentCapabilityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create agent capability",
    description="Create a new capability configuration for an agent",
)
async def create_agent_capability(
    agent_id: UUID,
    data: AgentCapabilityCreate,
    session: AsyncSession = Depends(get_db_async),
) -> AgentCapabilityResponse:
    """Create a new capability for an agent."""
    try:
        return await capability_service.create_agent_capability(session, agent_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        # Re-raise existing HTTPException
        raise


@router.get(
    "/agents/{agent_id}/capabilities",
    response_model=list[AgentCapabilityResponse],
    summary="List agent capabilities",
    description="Get all capabilities for an agent",
)
async def list_agent_capabilities(
    agent_id: UUID,
    enabled_only: bool = Query(
        False,
        description="Return only enabled capabilities",
    ),
    session: AsyncSession = Depends(get_db_async),
) -> list[AgentCapabilityResponse]:
    """List all capabilities for an agent."""
    return await capability_service.get_agent_capabilities(
        session, agent_id, enabled_only
    )


@router.get(
    "/agents/{agent_id}/capabilities/with-actions",
    response_model=list[CapabilityWithActions],
    summary="List capabilities with actions",
    description="Get all capabilities for an agent including their actions",
)
async def list_capabilities_with_actions(
    agent_id: UUID,
    channel: Optional[str] = Query(
        None,
        description="Filter actions by channel (SMS, VOICE, EMAIL)",
        pattern="^(SMS|VOICE|EMAIL|sms|voice|email)$",
    ),
    enabled_only: bool = Query(
        False,
        description="Return only enabled capabilities",
    ),
    session: AsyncSession = Depends(get_db_async),
) -> list[CapabilityWithActions]:
    """Get all capabilities with their actions for an agent."""
    return await capability_service.get_agent_capabilities_with_actions(
        session, agent_id, channel, enabled_only
    )


@router.put(
    "/capabilities/{capability_id}",
    response_model=AgentCapabilityResponse,
    summary="Update capability",
    description="Update a capability's priority or enabled status",
)
async def update_capability(
    capability_id: UUID,
    data: AgentCapabilityUpdate,
    session: AsyncSession = Depends(get_db_async),
) -> AgentCapabilityResponse:
    """Update a capability."""
    capability = await capability_service.update_agent_capability(
        session, capability_id, data
    )
    if not capability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {capability_id} not found",
        )
    return capability


@router.delete(
    "/capabilities/{capability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete capability",
    description="Delete a capability and all its actions",
)
async def delete_capability(
    capability_id: UUID,
    session: AsyncSession = Depends(get_db_async),
) -> None:
    """Delete a capability and all its actions."""
    deleted = await capability_service.delete_agent_capability(session, capability_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability {capability_id} not found",
        )


@router.post(
    "/capabilities/bulk-priority-update",
    response_model=BulkPriorityUpdateResponse,
    summary="Bulk update priorities",
    description="Update priorities for multiple capabilities at once",
)
async def bulk_update_priorities(
    data: BulkPriorityUpdate,
    session: AsyncSession = Depends(get_db_async),
) -> BulkPriorityUpdateResponse:
    """Bulk update capability priorities."""
    return await capability_service.bulk_update_priorities(session, data)


# ============= Capability Action Endpoints =============


@router.post(
    "/actions",
    response_model=ActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create capability action",
    description="Create a new action for a capability",
)
async def create_action(
    data: ActionCreate,
    session: AsyncSession = Depends(get_db_async),
) -> ActionResponse:
    """Create a new capability action."""
    try:
        return await capability_service.create_capability_action(
            session, data, "system"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        # Re-raise existing HTTPException
        raise


@router.get(
    "/capabilities/{capability_id}/actions",
    response_model=list[ActionResponse],
    summary="List capability actions",
    description="Get all actions for a capability",
)
async def list_capability_actions(
    capability_id: UUID,
    channel: Optional[str] = Query(
        None,
        description="Filter by channel (SMS, VOICE, EMAIL)",
        pattern="^(SMS|VOICE|EMAIL|sms|voice|email)$",
    ),
    session: AsyncSession = Depends(get_db_async),
) -> list[ActionResponse]:
    """List all actions for a capability."""
    return await capability_service.get_capability_actions(
        session, capability_id, channel
    )


@router.put(
    "/actions/{action_id}",
    response_model=ActionResponse,
    summary="Update action",
    description="Update a capability action",
)
async def update_action(
    action_id: UUID,
    data: ActionUpdate,
    session: AsyncSession = Depends(get_db_async),
) -> ActionResponse:
    """Update a capability action."""
    action = await capability_service.update_capability_action(
        session, action_id, data, "system"
    )
    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found",
        )
    return action


@router.delete(
    "/actions/{action_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete action",
    description="Delete a capability action",
)
async def delete_action(
    action_id: UUID,
    session: AsyncSession = Depends(get_db_async),
) -> None:
    """Delete a capability action."""
    deleted = await capability_service.delete_capability_action(
        session, action_id, "system"
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Action {action_id} not found",
        )
