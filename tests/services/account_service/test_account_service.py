"""Tests for AccountService.

Business focus: Prevent NULL constraint violations when doing partial account updates,
especially when updating subscription_id or other single fields.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from db.tables.accounts import AccountStatus, BusinessIndustry
from services.account_service import update_account
from services.account_service.schema import AccountParams
from services.auth_types import UserContext


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
def sample_account():
    """Sample account with required fields populated."""
    account = MagicMock()
    account.id = uuid.uuid4()
    account.name = "test-restaurant"
    account.display_name = "Test Restaurant"
    account.status = AccountStatus.active
    account.current_subscription_id = None
    account.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return account


class TestPartialAccountUpdate:
    """Tests to prevent NULL constraint violations on partial updates.

    Issue: When updating only certain fields (e.g., current_subscription_id),
    AccountParams defaults all other fields to None, causing the repository
    to attempt setting status=None, violating NOT NULL constraint.

    Fix: Filter out None values before passing to repository.
    """

    @patch("services.account_service._implementation.change_log_context")
    @patch("db.AccountRepository")
    def test_update_only_subscription_id_does_not_set_status_to_none(
        self,
        mock_repo_class,
        mock_change_log,
        mock_session,
        mock_context,
        sample_account,
    ):
        """
        Regression test: Updating only current_subscription_id should not
        attempt to set status=None.

        This was the production bug - when subscription service called
        update_account(AccountParams(current_subscription_id=uuid)),
        all other fields defaulted to None, including status, causing
        NOT NULL constraint violation.
        """
        # Setup
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_account.return_value = sample_account
        mock_repo.update_account.return_value = sample_account
        mock_change_log.return_value.__enter__.return_value = MagicMock()

        new_subscription_id = uuid.uuid4()

        # Act: Update only subscription_id
        params = AccountParams(current_subscription_id=new_subscription_id)
        result = update_account(
            session=mock_session,
            context=mock_context,
            account_name="test-restaurant",
            params=params,
        )

        # Assert: Repository was called with only non-None values
        update_call_kwargs = mock_repo.update_account.call_args[1]

        # Should have current_subscription_id
        assert "current_subscription_id" in update_call_kwargs
        assert update_call_kwargs["current_subscription_id"] == new_subscription_id

        # Should NOT have status in the update (filtered out because it was None)
        assert "status" not in update_call_kwargs

        # Should NOT have other None fields
        assert "display_name" not in update_call_kwargs
        assert "industry" not in update_call_kwargs

        assert result == sample_account

    @patch("services.account_service._implementation.change_log_context")
    @patch("db.AccountRepository")
    def test_update_multiple_fields_only_updates_provided_fields(
        self,
        mock_repo_class,
        mock_change_log,
        mock_session,
        mock_context,
        sample_account,
    ):
        """
        Verify that when updating multiple fields, only those fields
        are passed to repository, not all AccountParams fields.
        """
        # Setup
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_account.return_value = sample_account
        mock_repo.update_account.return_value = sample_account
        mock_change_log.return_value.__enter__.return_value = MagicMock()

        # Act: Update display_name and industry
        params = AccountParams(
            display_name="Updated Name", industry=BusinessIndustry.FOOD_BEVERAGE
        )
        update_account(
            session=mock_session,
            context=mock_context,
            account_name="test-restaurant",
            params=params,
        )

        # Assert: Only provided fields in update
        update_call_kwargs = mock_repo.update_account.call_args[1]

        assert "display_name" in update_call_kwargs
        assert update_call_kwargs["display_name"] == "Updated Name"

        assert "industry" in update_call_kwargs
        assert update_call_kwargs["industry"] == BusinessIndustry.FOOD_BEVERAGE

        # Should NOT have other None fields
        assert "status" not in update_call_kwargs
        assert "stripe_customer_id" not in update_call_kwargs
        assert "current_subscription_id" not in update_call_kwargs

    @patch("services.account_service._implementation.change_log_context")
    @patch("db.AccountRepository")
    def test_update_with_explicit_none_filters_it_out(
        self,
        mock_repo_class,
        mock_change_log,
        mock_session,
        mock_context,
        sample_account,
    ):
        """
        When a field is explicitly set to None in AccountParams,
        it should be filtered out (not passed to repository).

        This is by design - we don't support explicitly clearing fields
        via None in this pattern. To clear a field, you'd need a different
        mechanism (e.g., sentinel value or separate clear_fields param).
        """
        # Setup
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_account.return_value = sample_account
        mock_repo.update_account.return_value = sample_account
        mock_change_log.return_value.__enter__.return_value = MagicMock()

        # Act: Try to set display_name to None
        params = AccountParams(display_name=None)
        update_account(
            session=mock_session,
            context=mock_context,
            account_name="test-restaurant",
            params=params,
        )

        # Assert: None value was filtered out
        update_call_kwargs = mock_repo.update_account.call_args[1]
        assert "display_name" not in update_call_kwargs

    @patch("services.account_service._implementation.change_log_context")
    @patch("db.AccountRepository")
    def test_update_with_all_none_values_still_calls_repository(
        self,
        mock_repo_class,
        mock_change_log,
        mock_session,
        mock_context,
        sample_account,
    ):
        """
        Edge case: If all AccountParams fields are None (empty update),
        repository is still called but with empty kwargs.

        This allows version check and change logging to still happen.
        """
        # Setup
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_account.return_value = sample_account
        mock_repo.update_account.return_value = sample_account
        mock_change_log.return_value.__enter__.return_value = MagicMock()

        # Act: Update with all None values
        params = AccountParams()
        update_account(
            session=mock_session,
            context=mock_context,
            account_name="test-restaurant",
            params=params,
            expected_version=123,
        )

        # Assert: Repository was called with only account_name and expected_version
        call_args = mock_repo.update_account.call_args
        assert call_args[0] == ("test-restaurant", 123)  # positional args

        # No field updates in kwargs (all filtered out)
        assert len(call_args[1]) == 0

    @patch("services.account_service._implementation.change_log_context")
    @patch("db.AccountRepository")
    def test_update_status_field_works_when_explicitly_set(
        self,
        mock_repo_class,
        mock_change_log,
        mock_session,
        mock_context,
        sample_account,
    ):
        """
        Verify that status field CAN be updated when explicitly set
        to a non-None value.
        """
        # Setup
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_account.return_value = sample_account
        mock_repo.update_account.return_value = sample_account
        mock_change_log.return_value.__enter__.return_value = MagicMock()

        # Act: Explicitly update status
        params = AccountParams(status=AccountStatus.pending)
        update_account(
            session=mock_session,
            context=mock_context,
            account_name="test-restaurant",
            params=params,
        )

        # Assert: Status was included in update
        update_call_kwargs = mock_repo.update_account.call_args[1]
        assert "status" in update_call_kwargs
        assert update_call_kwargs["status"] == AccountStatus.pending


class TestAccountUpdateChangeLogging:
    """Verify change logging works correctly with filtered None values."""

    @patch("services.account_service._implementation.copy")
    @patch("services.account_service._implementation.change_log_context")
    @patch("db.AccountRepository")
    def test_change_logging_records_partial_update(
        self,
        mock_repo_class,
        mock_change_log,
        mock_copy,
        mock_session,
        mock_context,
        sample_account,
    ):
        """
        Change logging should work correctly even when only some fields
        are updated (None values filtered out).
        """
        # Setup
        old_account_copy = MagicMock()
        mock_copy.copy.return_value = old_account_copy
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        mock_repo.get_account.return_value = sample_account
        mock_repo.update_account.return_value = sample_account

        mock_ctx = MagicMock()
        mock_change_log.return_value.__enter__.return_value = mock_ctx

        # Act
        params = AccountParams(display_name="New Name")
        update_account(
            session=mock_session,
            context=mock_context,
            account_name="test-restaurant",
            params=params,
        )

        # Assert: Change log context was entered with old record
        mock_change_log.assert_called_once()
        assert mock_change_log.call_args[1]["old_record"] == old_account_copy

        # New record was set
        assert mock_ctx.new_record == sample_account
