"""Tests for ChangeLogRepository."""

import uuid
from unittest.mock import MagicMock

import pytest

from db.repositories.change_log_repository import ChangeLogRepository
from db.tables.change_log import ChangeAction, ChangeResourceType


@pytest.fixture
def mock_session():
    """Mock database session."""
    return MagicMock()


class TestChangeLogRepositoryEmptyChanges:
    """Test that change logs are created even with empty field changes."""

    def test_create_change_log_with_empty_changes(self, mock_session):
        """
        Verify that change logs are created even when changes list is empty.

        This is important for tracking operations that don't modify metadata
        but still represent significant actions (e.g., prompt content updates
        that create new versions without changing the Prompt record itself).
        """
        repo = ChangeLogRepository(mock_session)

        # Create a change log with no field changes
        change_log = repo.create_change_log(
            account_id=uuid.uuid4(),
            resource_type=ChangeResourceType.Prompt,
            resource_id="test-prompt-id",
            author="test@example.com",
            action=ChangeAction.Update,
            changes=[],  # Empty changes list
        )

        # Verify the change log was created (not None)
        assert (
            change_log is not None
        ), "Change log should be created even with empty changes"

        # Verify it was added to session
        mock_session.add.assert_called_once()

        # The change log should have been flushed
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once()

    def test_create_change_log_with_changes(self, mock_session):
        """
        Verify that change logs work normally with field changes.
        """
        from db.tables.change_log import ChangeField

        repo = ChangeLogRepository(mock_session)

        # Create a change log with field changes
        changes = [
            ChangeField(field="name", old_value="Old Name", new_value="New Name"),
            ChangeField(
                field="channel", old_value="['voice']", new_value="['voice', 'chat']"
            ),
        ]

        change_log = repo.create_change_log(
            account_id=uuid.uuid4(),
            resource_type=ChangeResourceType.Prompt,
            resource_id="test-prompt-id",
            author="test@example.com",
            action=ChangeAction.Update,
            changes=changes,
        )

        # Verify the change log was created
        assert change_log is not None

        # Verify field changes were added
        # The change log is added first, then each change field
        assert mock_session.add.call_count == 3  # 1 change_log + 2 changes
