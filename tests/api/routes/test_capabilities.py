"""
Tests for public capability routes
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import services.capability_service as capability_service
from api.routes.capabilities import create_action, delete_action, update_action
from services.capability_service.schema import (
    ActionCreate,
    ActionResponse,
    ActionUpdate,
)


@pytest.fixture
def mock_session(mocker):
    """Mock AsyncSession"""
    return mocker.AsyncMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_create_action_public(mocker, mock_session):
    """Test create_action on public route uses system author"""
    capability_id = uuid4()
    action_id = uuid4()

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

    mock_create = mocker.patch.object(
        capability_service,
        "create_capability_action",
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

    result = await create_action(data, mock_session)

    # Verify system author was used
    mock_create.assert_called_once_with(mock_session, data, "system")
    assert result.action == "test_action"


@pytest.mark.asyncio
async def test_update_action_public(mocker, mock_session):
    """Test update_action on public route uses system author"""
    from datetime import datetime, timezone

    from services.capability_service.schema import ActionResponse

    action_id = uuid4()

    # Mock service response
    mock_response = ActionResponse(
        id=action_id,
        agent_capability_id=uuid4(),
        action="test_action",
        prompt="updated prompt",
        channel="VOICE",
        priority=1,
        enabled=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_update = mocker.patch.object(
        capability_service,
        "update_capability_action",
        return_value=mock_response,
    )

    data = ActionUpdate(
        prompt="updated prompt", channel=None, priority=None, enabled=None
    )

    result = await update_action(action_id, data, mock_session)

    # Verify system author was used
    mock_update.assert_called_once_with(mock_session, action_id, data, "system")
    assert result.prompt == "updated prompt"


@pytest.mark.asyncio
async def test_delete_action_public(mocker, mock_session):
    """Test delete_action on public route uses system author"""
    action_id = uuid4()

    # Mock service response
    mock_delete = mocker.patch.object(
        capability_service,
        "delete_capability_action",
        return_value=True,
    )

    await delete_action(action_id, mock_session)

    # Verify system author was used
    mock_delete.assert_called_once_with(mock_session, action_id, "system")
