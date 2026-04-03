"""
Tests for capability action change tracking
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import db
from db.tables import Agent, AgentCapability, CapabilityAction
from db.tables.change_log import ChangeField, ChangeResourceType
from services.capability_service._implementation import (
    create_capability_action,
    delete_capability_action,
    update_capability_action,
)
from services.capability_service.schema import ActionCreate, ActionUpdate
from services.history_service._implementation import create_change_log


@pytest.fixture
def mock_async_session(mocker):
    """Mock AsyncSession"""
    session = mocker.AsyncMock(spec=AsyncSession)
    session.run_sync = mocker.AsyncMock()
    return session


@pytest.fixture
def mock_capability():
    """Mock AgentCapability"""
    capability = MagicMock(spec=AgentCapability)
    capability.id = uuid4()
    capability.agent_id = uuid4()
    capability.capability_identifier = "communication_style"
    return capability


@pytest.fixture
def mock_agent():
    """Mock Agent"""
    agent = MagicMock(spec=Agent)
    agent.id = uuid4()
    agent.account_id = uuid4()
    return agent


@pytest.fixture
def mock_action():
    """Mock CapabilityAction"""
    action = MagicMock(spec=CapabilityAction)
    action.id = uuid4()
    action.agent_capability_id = uuid4()
    action.action = "test_action"
    action.prompt = "test prompt"
    action.channel = "VOICE"
    action.priority = 1
    action.enabled = True
    return action


def test_create_change_log_with_extra_fields():
    """Test that extra_fields are appended to the change log fields."""
    mock_session = MagicMock()
    mock_repo = MagicMock()
    mock_repo.create_change_log.return_value = MagicMock()

    extra = ChangeField(
        field="section", old_value=None, new_value="communication_style"
    )

    with patch(
        "services.history_service._implementation.ChangeLogRepository",
        return_value=mock_repo,
    ):
        create_change_log(
            session=mock_session,
            account_id=uuid4(),
            resource_type=ChangeResourceType.CapabilityAction,
            resource_id=str(uuid4()),
            author="test@example.com",
            old_record=None,
            new_record=None,
            extra_fields=[extra],
        )

    called_changes = mock_repo.create_change_log.call_args.kwargs["changes"]
    assert any(
        f.field == "section" and f.new_value == "communication_style"
        for f in called_changes
    )


@pytest.mark.asyncio
async def test_create_capability_action_creates_change_log(
    mocker, mock_async_session, mock_capability, mock_agent, mock_action
):
    """Test that create_capability_action creates a change log entry with snapshots"""
    # Setup mocks
    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(return_value=mock_capability)
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    mock_agent_repo = mocker.Mock()
    mock_agent_repo.get_agent = mocker.AsyncMock(return_value=mock_agent)
    mocker.patch.object(db, "AgentRepositoryAsync", return_value=mock_agent_repo)

    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_capability_and_action = mocker.AsyncMock(return_value=None)
    mock_action_repo.create = mocker.AsyncMock(return_value=mock_action)
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    # Patch _snapshot_columns since CapabilityAction.__table__ doesn't work on MagicMock
    new_snap = SimpleNamespace(
        id=mock_action.id,
        action="test_action",
        prompt="test prompt",
        channel="VOICE",
        priority=1,
        enabled=True,
    )
    mocker.patch(
        "services.capability_service._implementation._snapshot_columns",
        return_value=new_snap,
    )

    # Create action
    data = ActionCreate(
        agent_capability_id=mock_capability.id,
        action="test_action",
        prompt="test prompt",
        channel="VOICE",
        priority=1,
        enabled=True,
    )
    author = "test@example.com"

    result = await create_capability_action(mock_async_session, data, author)

    # Verify change log was created via run_sync with snapshot, not ORM object
    assert mock_async_session.run_sync.called
    assert result.action == "test_action"


@pytest.mark.asyncio
async def test_update_capability_action_creates_change_log(
    mocker, mock_async_session, mock_capability, mock_agent, mock_action
):
    """Test that update_capability_action creates a change log entry"""
    # Setup mocks
    old_action = MagicMock(spec=CapabilityAction)
    old_action.id = mock_action.id
    old_action.agent_capability_id = mock_capability.id
    old_action.prompt = "old prompt"

    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=old_action)
    mock_action_repo.update = mocker.AsyncMock(return_value=mock_action)
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(return_value=mock_capability)
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    mock_agent_repo = mocker.Mock()
    mock_agent_repo.get_agent = mocker.AsyncMock(return_value=mock_agent)
    mocker.patch.object(db, "AgentRepositoryAsync", return_value=mock_agent_repo)

    # Patch _snapshot_columns since CapabilityAction.__table__ doesn't work on MagicMock
    mocker.patch(
        "services.capability_service._implementation._snapshot_columns",
        return_value=MagicMock(prompt="old prompt"),
    )

    # Update action
    data = ActionUpdate(prompt="new prompt", channel=None, priority=None, enabled=None)
    author = "test@example.com"

    result = await update_capability_action(
        mock_async_session, mock_action.id, data, author
    )

    # Verify change log was created
    assert mock_async_session.run_sync.called
    assert result is not None


@pytest.mark.asyncio
async def test_delete_capability_action_creates_change_log(
    mocker, mock_async_session, mock_capability, mock_agent, mock_action
):
    """Test that delete_capability_action creates a change log entry with snapshots"""
    # Setup mocks
    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=mock_action)
    mock_action_repo.delete = mocker.AsyncMock(return_value=True)
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(return_value=mock_capability)
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    mock_agent_repo = mocker.Mock()
    mock_agent_repo.get_agent = mocker.AsyncMock(return_value=mock_agent)
    mocker.patch.object(db, "AgentRepositoryAsync", return_value=mock_agent_repo)

    # Patch _snapshot_columns since CapabilityAction.__table__ doesn't work on MagicMock
    old_snap = SimpleNamespace(
        id=mock_action.id,
        action="test_action",
        prompt="test prompt",
        channel="VOICE",
        priority=1,
        enabled=True,
    )
    mocker.patch(
        "services.capability_service._implementation._snapshot_columns",
        return_value=old_snap,
    )

    # Delete action
    author = "test@example.com"

    result = await delete_capability_action(mock_async_session, mock_action.id, author)

    # Verify change log was created via run_sync with snapshot, not ORM object
    assert mock_async_session.run_sync.called
    assert result is True


@pytest.mark.asyncio
async def test_create_capability_action_invalid_capability(mocker, mock_async_session):
    """Test that create_capability_action raises ValueError for invalid capability"""
    # Setup mocks - capability not found
    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(return_value=None)
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    # Create action
    data = ActionCreate(
        agent_capability_id=uuid4(),
        action="test_action",
        prompt="test prompt",
        channel="VOICE",
        priority=1,
        enabled=True,
    )
    author = "test@example.com"

    with pytest.raises(ValueError, match="not found"):
        await create_capability_action(mock_async_session, data, author)


@pytest.mark.asyncio
async def test_update_capability_action_not_found(mocker, mock_async_session):
    """Test that update_capability_action returns None for non-existent action"""
    # Setup mocks - action not found
    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=None)
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    # Update action
    data = ActionUpdate(prompt="new prompt", channel=None, priority=None, enabled=None)
    author = "test@example.com"

    result = await update_capability_action(mock_async_session, uuid4(), data, author)

    assert result is None


@pytest.mark.asyncio
async def test_delete_capability_action_not_found(mocker, mock_async_session):
    """Test that delete_capability_action returns False for non-existent action"""
    # Setup mocks - action not found
    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=None)
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    # Delete action
    author = "test@example.com"

    result = await delete_capability_action(mock_async_session, uuid4(), author)

    assert result is False


@pytest.mark.asyncio
async def test_create_capability_action_agent_not_found(
    mocker, mock_async_session, mock_capability
):
    """Test that create_capability_action raises ValueError when agent not found"""
    # Setup mocks
    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(return_value=mock_capability)
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    mock_agent_repo = mocker.Mock()
    mock_agent_repo.get_agent = mocker.AsyncMock(return_value=None)  # Agent not found
    mocker.patch.object(db, "AgentRepositoryAsync", return_value=mock_agent_repo)

    # Create action
    data = ActionCreate(
        agent_capability_id=mock_capability.id,
        action="test_action",
        prompt="test prompt",
        channel="VOICE",
        priority=1,
        enabled=True,
    )
    author = "test@example.com"

    with pytest.raises(ValueError, match="Agent .* not found"):
        await create_capability_action(mock_async_session, data, author)


@pytest.mark.asyncio
async def test_update_capability_action_no_fields_to_update(
    mocker, mock_async_session, mock_action
):
    """Test that update_capability_action returns existing action when no fields to update"""
    # Setup mocks
    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=mock_action)
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    # Patch _snapshot_columns since CapabilityAction.__table__ doesn't work on MagicMock
    mocker.patch(
        "services.capability_service._implementation._snapshot_columns",
        return_value=MagicMock(),
    )

    # Update with no fields
    data = ActionUpdate(
        prompt=None, channel=None, priority=None, enabled=None
    )  # Empty update
    author = "test@example.com"

    result = await update_capability_action(
        mock_async_session, mock_action.id, data, author
    )

    # Should return existing action without calling update
    assert result is not None
    assert result.action == "test_action"


@pytest.mark.asyncio
async def test_update_capability_action_capability_not_found(
    mocker, mock_async_session, mock_action
):
    """Test that update_capability_action returns None when capability not found"""
    # Setup mocks
    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=mock_action)
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    # Patch _snapshot_columns since CapabilityAction.__table__ doesn't work on MagicMock
    mocker.patch(
        "services.capability_service._implementation._snapshot_columns",
        return_value=MagicMock(),
    )

    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(
        return_value=None
    )  # Capability not found
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    # Update action
    data = ActionUpdate(prompt="new prompt", channel=None, priority=None, enabled=None)
    author = "test@example.com"

    result = await update_capability_action(
        mock_async_session, mock_action.id, data, author
    )

    assert result is None


@pytest.mark.asyncio
async def test_update_capability_action_update_fails(
    mocker, mock_async_session, mock_capability, mock_agent, mock_action
):
    """Test that update_capability_action returns None when update operation fails"""
    # Setup mocks
    old_action = MagicMock(spec=CapabilityAction)
    old_action.id = mock_action.id
    old_action.agent_capability_id = mock_capability.id

    # Patch _snapshot_columns since CapabilityAction.__table__ doesn't work on MagicMock
    mocker.patch(
        "services.capability_service._implementation._snapshot_columns",
        return_value=MagicMock(prompt="old prompt"),
    )

    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=old_action)
    mock_action_repo.update = mocker.AsyncMock(return_value=None)  # Update fails
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(return_value=mock_capability)
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    mock_agent_repo = mocker.Mock()
    mock_agent_repo.get_agent = mocker.AsyncMock(return_value=mock_agent)
    mocker.patch.object(db, "AgentRepositoryAsync", return_value=mock_agent_repo)

    # Update action
    data = ActionUpdate(prompt="new prompt", channel=None, priority=None, enabled=None)
    author = "test@example.com"

    result = await update_capability_action(
        mock_async_session, mock_action.id, data, author
    )

    assert result is None


@pytest.mark.asyncio
async def test_delete_capability_action_capability_not_found(
    mocker, mock_async_session, mock_action
):
    """Test that delete_capability_action returns False when capability not found"""
    # Setup mocks
    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=mock_action)
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(
        return_value=None
    )  # Capability not found
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    # Delete action
    author = "test@example.com"

    result = await delete_capability_action(mock_async_session, mock_action.id, author)

    assert result is False


@pytest.mark.asyncio
async def test_delete_capability_action_agent_not_found(
    mocker, mock_async_session, mock_capability, mock_action
):
    """Test that delete_capability_action returns False when agent not found"""
    # Setup mocks
    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=mock_action)
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(return_value=mock_capability)
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    mock_agent_repo = mocker.Mock()
    mock_agent_repo.get_agent = mocker.AsyncMock(return_value=None)  # Agent not found
    mocker.patch.object(db, "AgentRepositoryAsync", return_value=mock_agent_repo)

    # Delete action
    author = "test@example.com"

    result = await delete_capability_action(mock_async_session, mock_action.id, author)

    assert result is False


@pytest.mark.asyncio
async def test_delete_capability_action_delete_fails(
    mocker, mock_async_session, mock_capability, mock_agent, mock_action
):
    """Test that delete_capability_action returns False when delete operation fails"""
    # Setup mocks
    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=mock_action)
    mock_action_repo.delete = mocker.AsyncMock(return_value=False)  # Delete fails
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(return_value=mock_capability)
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    mock_agent_repo = mocker.Mock()
    mock_agent_repo.get_agent = mocker.AsyncMock(return_value=mock_agent)
    mocker.patch.object(db, "AgentRepositoryAsync", return_value=mock_agent_repo)

    # Patch _snapshot_columns since CapabilityAction.__table__ doesn't work on MagicMock
    mocker.patch(
        "services.capability_service._implementation._snapshot_columns",
        return_value=SimpleNamespace(),
    )

    # Delete action
    author = "test@example.com"

    result = await delete_capability_action(mock_async_session, mock_action.id, author)

    assert result is False


@pytest.mark.asyncio
async def test_run_sync_receives_snapshots_not_orm_objects(
    mocker, mock_async_session, mock_capability, mock_agent, mock_action
):
    """Verify that run_sync callback receives SimpleNamespace snapshots and plain values,
    never expired ORM objects. This is the core fix: after repo.commit() all ORM objects
    in the session are expired, so passing them to run_sync causes DetachedInstanceError.
    """
    # Setup mocks
    mock_cap_repo = mocker.Mock()
    mock_cap_repo.get_by_id = mocker.AsyncMock(return_value=mock_capability)
    mocker.patch.object(
        db, "AgentCapabilityRepositoryAsync", return_value=mock_cap_repo
    )

    mock_agent_repo = mocker.Mock()
    mock_agent_repo.get_agent = mocker.AsyncMock(return_value=mock_agent)
    mocker.patch.object(db, "AgentRepositoryAsync", return_value=mock_agent_repo)

    mock_action_repo = mocker.Mock()
    mock_action_repo.get_by_id = mocker.AsyncMock(return_value=mock_action)
    mock_action_repo.update = mocker.AsyncMock(return_value=mock_action)
    mocker.patch.object(
        db, "CapabilityActionRepositoryAsync", return_value=mock_action_repo
    )

    old_snap = SimpleNamespace(prompt="old prompt", id=mock_action.id)
    new_snap = SimpleNamespace(prompt="new prompt", id=mock_action.id)
    snapshot_calls = [old_snap, new_snap]
    mocker.patch(
        "services.capability_service._implementation._snapshot_columns",
        side_effect=snapshot_calls,
    )

    data = ActionUpdate(prompt="new prompt", channel=None, priority=None, enabled=None)
    await update_capability_action(
        mock_async_session, mock_action.id, data, "test@example.com"
    )

    # Extract the lambda passed to run_sync and inspect its closure values
    assert mock_async_session.run_sync.called
    run_sync_call = mock_async_session.run_sync.call_args
    callback = run_sync_call[0][0]

    # Call the callback with a mock sync session to capture args to create_change_log
    mock_sync_session = MagicMock()
    with patch(
        "services.capability_service._implementation.create_change_log"
    ) as mock_create_cl:
        callback(mock_sync_session)

        call_kwargs = mock_create_cl.call_args.kwargs
        # old_record and new_record must be SimpleNamespace, not ORM objects
        assert isinstance(call_kwargs["old_record"], SimpleNamespace)
        assert isinstance(call_kwargs["new_record"], SimpleNamespace)
        # account_id must be a plain UUID, not an ORM attribute accessor
        assert call_kwargs["account_id"] == mock_agent.account_id
        # model_class must be passed so _inspect_field_changes can get the mapper
        assert call_kwargs["model_class"] is CapabilityAction
