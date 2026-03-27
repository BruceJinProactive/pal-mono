"""
Tests for admin capability implementation functions
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.admin._capabilities import create_action, delete_action, update_action
from services.auth_types import UserContext
from services.capability_service.schema import (
    ActionCreate,
    ActionResponse,
    ActionUpdate,
)


@pytest.fixture
def mock_context():
    """Mock UserContext"""
    context = MagicMock(spec=UserContext)
    context.email = "test@example.com"
    context.account_id = uuid4()
    return context


@pytest.fixture
def mock_session(mocker):
    """Mock AsyncSession"""
    return mocker.AsyncMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_create_action_success(mocker, mock_context, mock_session):
    """Test create_action successfully creates an action"""
    agent_id = uuid4()
    capability_id = uuid4()
    action_id = uuid4()

    # Mock capability repository
    mock_capability = MagicMock()
    mock_capability.agent_id = agent_id

    mock_cap_repo = MagicMock()
    mock_cap_repo.get_by_id = AsyncMock(return_value=mock_capability)
    mocker.patch(
        "api.routes.admin._capabilities.AgentCapabilityRepositoryAsync",
        return_value=mock_cap_repo,
    )

    # Mock service response
    mock_response = ActionResponse(
        id=action_id,
        agent_capability_id=capability_id,
        action="test_action",
        prompt="test prompt",
        channel="VOICE",
        priority=1,
        enabled=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mocker.patch(
        "api.routes.admin._capabilities.capability_service.create_capability_action",
        return_value=mock_response,
    )

    data = ActionCreate(
        agent_capability_id=capability_id,
        action="test_action",
        prompt="test prompt",
        channel="VOICE",
        priority=1,
        enabled=True,
    )

    result = await create_action(agent_id, data, mock_context, mock_session)
    assert result.action == "test_action"


@pytest.mark.asyncio
async def test_update_action_success(mocker, mock_context, mock_session):
    """Test update_action successfully updates an action"""
    agent_id = uuid4()
    action_id = uuid4()
    capability_id = uuid4()

    # Mock action repository
    mock_action = MagicMock()
    mock_action.agent_capability_id = capability_id

    mock_action_repo = MagicMock()
    mock_action_repo.get_by_id = AsyncMock(return_value=mock_action)
    mocker.patch(
        "api.routes.admin._capabilities.CapabilityActionRepositoryAsync",
        return_value=mock_action_repo,
    )

    # Mock capability repository
    mock_capability = MagicMock()
    mock_capability.agent_id = agent_id

    mock_cap_repo = MagicMock()
    mock_cap_repo.get_by_id = AsyncMock(return_value=mock_capability)
    mocker.patch(
        "api.routes.admin._capabilities.AgentCapabilityRepositoryAsync",
        return_value=mock_cap_repo,
    )

    # Mock service response
    mock_response = ActionResponse(
        id=action_id,
        agent_capability_id=capability_id,
        action="test_action",
        prompt="updated prompt",
        channel="VOICE",
        priority=1,
        enabled=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mocker.patch(
        "api.routes.admin._capabilities.capability_service.update_capability_action",
        return_value=mock_response,
    )

    data = ActionUpdate(
        prompt="updated prompt", channel=None, priority=None, enabled=None
    )

    result = await update_action(agent_id, action_id, data, mock_context, mock_session)
    assert result.prompt == "updated prompt"


@pytest.mark.asyncio
async def test_delete_action_success(mocker, mock_context, mock_session):
    """Test delete_action successfully deletes an action"""
    agent_id = uuid4()
    action_id = uuid4()
    capability_id = uuid4()

    # Mock action repository
    mock_action = MagicMock()
    mock_action.agent_capability_id = capability_id

    mock_action_repo = MagicMock()
    mock_action_repo.get_by_id = AsyncMock(return_value=mock_action)
    mocker.patch(
        "api.routes.admin._capabilities.CapabilityActionRepositoryAsync",
        return_value=mock_action_repo,
    )

    # Mock capability repository
    mock_capability = MagicMock()
    mock_capability.agent_id = agent_id

    mock_cap_repo = MagicMock()
    mock_cap_repo.get_by_id = AsyncMock(return_value=mock_capability)
    mocker.patch(
        "api.routes.admin._capabilities.AgentCapabilityRepositoryAsync",
        return_value=mock_cap_repo,
    )

    # Mock service response
    mocker.patch(
        "api.routes.admin._capabilities.capability_service.delete_capability_action",
        return_value=True,
    )

    await delete_action(agent_id, action_id, mock_context, mock_session)
    # No exception means success
