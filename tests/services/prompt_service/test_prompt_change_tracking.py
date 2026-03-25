"""Tests for prompt service change tracking.

Business focus: Ensure that prompt CRUD operations (create, update, delete)
properly track changes in the edit history system.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from db.tables.change_log import ChangeResourceType
from services.auth_types import UserContext
from services.prompt_service import delete_prompt, update_prompt


@pytest.fixture
def mock_session():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def mock_context():
    """Mock user context."""
    context = MagicMock(spec=UserContext)
    context.email = "admin@example.com"
    context.account_id = uuid.uuid4()
    return context


@pytest.fixture
def sample_prompt():
    """Sample prompt record (original state)."""
    prompt = MagicMock()
    prompt.id = uuid.uuid4()
    prompt.name = "Test Prompt"
    prompt.resource_type = "agent"
    prompt.resource_id = uuid.uuid4()
    prompt.channel = ["voice"]
    prompt.default_prompt_id = None
    return prompt


@pytest.fixture
def updated_prompt(sample_prompt):
    """Sample prompt record after updates (distinct instance)."""
    prompt = MagicMock()
    prompt.id = sample_prompt.id  # Same ID
    prompt.name = "Updated Test Prompt"  # Changed
    prompt.resource_type = sample_prompt.resource_type
    prompt.resource_id = sample_prompt.resource_id
    prompt.channel = sample_prompt.channel
    prompt.default_prompt_id = sample_prompt.default_prompt_id
    return prompt


@pytest.fixture
def sample_account():
    """Sample account record."""
    account = MagicMock()
    account.id = uuid.uuid4()
    account.name = "test-account"
    return account


@pytest.fixture
def sample_agent():
    """Sample agent record."""
    agent = MagicMock()
    agent.id = uuid.uuid4()
    agent.account_id = uuid.uuid4()
    return agent


class TestPromptUpdateChangeTracking:
    """Tests to ensure prompt updates are properly tracked in change history."""

    @patch("services.prompt_service._implementation.change_log_context")
    @patch("services.prompt_service._implementation.PromptRepository")
    @patch("services.prompt_service._implementation.account_service")
    @patch("services.prompt_service._implementation.agent_service")
    def test_update_prompt_sets_old_record_in_context(
        self,
        mock_agent_service,
        mock_account_service,
        mock_repo_class,
        mock_change_log,
        mock_session,
        mock_context,
        sample_account,
        sample_agent,
        sample_prompt,
        updated_prompt,
    ):
        """
        Verify that update_prompt sets ctx.old_record before updating.
        This is required for proper change diffing in edit history.
        """
        # Setup - ensure agent belongs to the account
        sample_agent.account_id = sample_account.id
        mock_account_service.get_account.return_value = sample_account
        mock_agent_service.get_agent.return_value = sample_agent
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_prompt_by_id.return_value = sample_prompt

        # Mock the context manager
        mock_ctx = MagicMock()
        mock_change_log.return_value.__enter__.return_value = mock_ctx

        # Capture state at the time of repository update
        old_record_at_update = None

        def capture_update(*args, **kwargs):
            nonlocal old_record_at_update
            old_record_at_update = mock_ctx.old_record
            return updated_prompt

        mock_repo.update_prompt.side_effect = capture_update
        mock_repo.get_next_version_number.return_value = 2

        # Execute
        update_prompt(
            session=mock_session,
            context=mock_context,
            account_name="test-account",
            prompt_id=sample_prompt.id,
            name="Updated Name",
            content="New content",
            auto_commit=True,
        )

        # Verify old_record was set BEFORE repository update
        assert (
            old_record_at_update == sample_prompt
        ), "ctx.old_record must be set BEFORE update_prompt is called"
        assert mock_ctx.resource_id == str(
            sample_prompt.id
        ), "ctx.resource_id should be set"

        # Verify new_record is the updated instance
        assert (
            mock_ctx.new_record == updated_prompt
        ), "ctx.new_record should be the updated prompt instance"
        assert (
            mock_ctx.new_record != sample_prompt
        ), "new_record should be distinct from old_record"

    @patch("services.prompt_service._implementation.change_log_context")
    @patch("services.prompt_service._implementation.PromptRepository")
    @patch("services.prompt_service._implementation.account_service")
    @patch("services.prompt_service._implementation.agent_service")
    def test_update_prompt_content_only_tracks_changes(
        self,
        mock_agent_service,
        mock_account_service,
        mock_repo_class,
        mock_change_log,
        mock_session,
        mock_context,
        sample_account,
        sample_agent,
        sample_prompt,
    ):
        """
        Regression test: Content-only updates should create change log entries.

        Previously, ctx.resource_id was only set when metadata changed,
        causing content-only updates to be skipped (resource_id was None).
        """
        # Setup - ensure agent belongs to the account
        sample_agent.account_id = sample_account.id
        mock_account_service.get_account.return_value = sample_account
        mock_agent_service.get_agent.return_value = sample_agent
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_prompt_by_id.return_value = sample_prompt
        mock_repo.get_next_version_number.return_value = 2

        mock_ctx = MagicMock()
        mock_change_log.return_value.__enter__.return_value = mock_ctx

        # Capture old_record timing
        old_record_before_content_update = None

        def capture_version(*args, **kwargs):
            nonlocal old_record_before_content_update
            old_record_before_content_update = mock_ctx.old_record
            return None

        mock_repo.create_prompt_details.side_effect = capture_version

        # Execute: Update ONLY content (no metadata changes)
        update_prompt(
            session=mock_session,
            context=mock_context,
            account_name="test-account",
            prompt_id=sample_prompt.id,
            content="Updated content only",
            auto_commit=True,
        )

        # Verify: old_record was set before content update
        assert (
            old_record_before_content_update == sample_prompt
        ), "ctx.old_record must be set before creating new content version"

        # Verify: ctx.resource_id is set even when no metadata changes
        assert mock_ctx.resource_id == str(
            sample_prompt.id
        ), "ctx.resource_id must be set for content-only updates to be tracked"

        # When only content changes, the Prompt record is unchanged
        assert (
            mock_ctx.new_record == sample_prompt
        ), "new_record equals old when only content changes (metadata unchanged)"


class TestPromptDeleteChangeTracking:
    """Tests to ensure prompt deletions are properly tracked in change history."""

    @patch("services.prompt_service._implementation.change_log_context")
    @patch("services.prompt_service._implementation.PromptRepository")
    @patch("services.prompt_service._implementation.account_service")
    @patch("services.prompt_service._implementation.agent_service")
    def test_delete_prompt_sets_old_record_in_context(
        self,
        mock_agent_service,
        mock_account_service,
        mock_repo_class,
        mock_change_log,
        mock_session,
        mock_context,
        sample_account,
        sample_agent,
        sample_prompt,
    ):
        """
        Verify that delete_prompt sets ctx.old_record before deletion.
        This is required for change history to show what was deleted.
        """
        # Setup - ensure agent belongs to the account
        sample_agent.account_id = sample_account.id
        mock_account_service.get_account.return_value = sample_account
        mock_agent_service.get_agent.return_value = sample_agent
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_prompt_by_id.return_value = sample_prompt

        mock_ctx = MagicMock()
        mock_change_log.return_value.__enter__.return_value = mock_ctx

        # Capture old_record at time of deletion
        old_record_at_delete = None

        def capture_delete(*args, **kwargs):
            nonlocal old_record_at_delete
            old_record_at_delete = mock_ctx.old_record
            return True

        mock_repo.delete_prompt.side_effect = capture_delete

        # Execute
        delete_prompt(
            session=mock_session,
            context=mock_context,
            account_name="test-account",
            prompt_id=sample_prompt.id,
            auto_commit=True,
        )

        # Verify old_record was set BEFORE deletion
        assert (
            old_record_at_delete == sample_prompt
        ), "ctx.old_record must be set BEFORE delete_prompt is called"
        assert mock_ctx.resource_id == str(
            sample_prompt.id
        ), "ctx.resource_id should be set"
        assert (
            mock_ctx.new_record is None
        ), "ctx.new_record should be None for deletions"


class TestChangeLogContextProperties:
    """Tests for ChangeLogContext old_record property."""

    @patch("services.history_service._context.create_change_log")
    def test_change_log_context_old_record_property(self, mock_create_log):
        """
        Verify that ChangeLogContext.old_record property can be get/set.
        This covers the property getter and setter at lines 50, 54 in _context.py.
        """
        from services.history_service._context import ChangeLogContext

        mock_session = MagicMock()
        mock_old_record = MagicMock()
        mock_new_record = MagicMock()

        # Create context and set old_record via property setter
        ctx = ChangeLogContext(
            session=mock_session,
            resource_type=ChangeResourceType.Prompt,
            author="test@example.com",
            account_id=uuid.uuid4(),
            resource_id="test-id",
            auto_commit=False,
        )

        # Test setter (line 54)
        ctx.old_record = mock_old_record

        # Test getter (line 50)
        assert ctx.old_record == mock_old_record

        # Test setting to None (also exercises getter/setter)
        ctx.old_record = None
        assert ctx.old_record is None

        # Reset to mock value for context manager test
        ctx.old_record = mock_old_record

        # Also test it works in context manager
        ctx.new_record = mock_new_record
        with ctx:
            pass

        # Verify create_change_log was called with our old_record
        mock_create_log.assert_called_once()
        call_kwargs = mock_create_log.call_args[1]
        assert call_kwargs["old_record"] == mock_old_record
        assert call_kwargs["new_record"] == mock_new_record
