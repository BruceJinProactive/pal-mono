"""Tests for AccountRepository and AccountRepositoryAsync.

Business focus: Multi-tenant account lifecycle — lookup, creation,
updates with optimistic locking, soft/hard deletion, and admin filtering.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.account_repository import AccountRepository, AccountRepositoryAsync
from db.tables import Account, Conversation, User
from db.tables.accounts import AccountStatus
from db.tables.types import SubscriptionStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = MagicMock()
    mock_query = MagicMock()
    session.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.options.return_value = mock_query
    mock_query.outerjoin.return_value = mock_query
    mock_query.join.return_value = mock_query
    mock_query.having.return_value = mock_query
    mock_query.group_by.return_value = mock_query
    return session


@pytest.fixture
def mock_async_session():
    return AsyncMock()


@pytest.fixture
def repo(mock_session):
    return AccountRepository(mock_session)


@pytest.fixture
def repo_no_commit(mock_session):
    return AccountRepository(mock_session, auto_commit=False)


@pytest.fixture
def async_repo(mock_async_session):
    return AccountRepositoryAsync(mock_async_session)


@pytest.fixture
def sample_account_id():
    return uuid.uuid4()


@pytest.fixture
def sample_account(sample_account_id):
    account = MagicMock(spec=Account)
    account.id = sample_account_id
    account.name = "test-restaurant"
    account.display_name = "Test Restaurant"
    account.status = AccountStatus.active
    account.stripe_coupon_id = None
    account.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return account


# ---------------------------------------------------------------------------
# TestAccountLookup — Tenant resolution
# ---------------------------------------------------------------------------


class TestAccountLookup:
    """Core tenant resolution: every API request must resolve which account
    is being accessed. Deleted accounts must never be returned."""

    def test_get_account_by_name_returns_account(
        self, repo, mock_session, sample_account
    ):
        """Restaurant operator logs in by account name."""
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            sample_account
        ]
        result = repo.get_account("test-restaurant")
        assert result == sample_account

    def test_get_account_by_name_returns_none_when_not_found(self, repo, mock_session):
        """Nonexistent account name returns None gracefully."""
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )
        result = repo.get_account("nonexistent")
        assert result is None

    def test_get_account_by_name_returns_none_on_db_error(self, repo, mock_session):
        """DB error returns empty list from get_accounts_by_names, so get_account returns None."""
        mock_session.query.return_value.filter.return_value.filter.return_value.all.side_effect = SQLAlchemyError(
            "connection lost"
        )
        result = repo.get_account("test")
        assert result is None
        mock_session.rollback.assert_called_once()

    def test_get_account_by_id_returns_account(
        self, repo, mock_session, sample_account, sample_account_id
    ):
        """Internal ID-based lookup for API operations."""
        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            sample_account
        )
        result = repo.get_account_by_id(sample_account_id)
        assert result == sample_account

    def test_get_account_by_id_returns_none_when_not_found(
        self, repo, mock_session, sample_account_id
    ):
        """Nonexistent account ID returns None."""
        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            None
        )
        result = repo.get_account_by_id(sample_account_id)
        assert result is None

    def test_get_account_by_id_returns_none_on_db_error(
        self, repo, mock_session, sample_account_id
    ):
        """Graceful failure on database error."""
        mock_session.query.return_value.filter.return_value.filter.return_value.first.side_effect = SQLAlchemyError(
            "timeout"
        )
        result = repo.get_account_by_id(sample_account_id)
        assert result is None
        mock_session.rollback.assert_called_once()

    def test_get_accounts_by_names_returns_multiple(
        self, repo, mock_session, sample_account
    ):
        """Batch lookup for admin operations."""
        account2 = MagicMock(spec=Account)
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            sample_account,
            account2,
        ]
        result = repo.get_accounts_by_names(["test-restaurant", "other-restaurant"])
        assert len(result) == 2

    def test_get_accounts_by_names_returns_empty_on_error(self, repo, mock_session):
        """Error resilience for batch operations."""
        mock_session.query.return_value.filter.return_value.filter.return_value.all.side_effect = SQLAlchemyError(
            "error"
        )
        result = repo.get_accounts_by_names(["test"])
        assert result == []
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# TestAccountCreation — Onboarding
# ---------------------------------------------------------------------------


class TestAccountCreation:
    """Onboarding new restaurant businesses. Duplicate prevention is critical
    to avoid billing and routing errors."""

    def test_create_account_success(self, repo, mock_session):
        """New restaurant signs up."""
        # get_account returns None (no existing)
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )
        result = repo.create_account("new-restaurant")
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()
        assert isinstance(result, Account)

    def test_create_account_returns_existing_if_name_taken(
        self, repo, mock_session, sample_account
    ):
        """Prevents duplicate accounts — idempotent creation."""
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            sample_account
        ]
        result = repo.create_account("test-restaurant")
        assert result == sample_account
        mock_session.add.assert_not_called()

    def test_create_account_sets_additional_kwargs(self, repo, mock_session):
        """Display name, industry, and other onboarding fields set correctly."""
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )
        result = repo.create_account(
            "new-restaurant", display_name="New Restaurant", industry="food_beverage"
        )
        assert isinstance(result, Account)

    def test_create_account_uses_flush_when_auto_commit_off(
        self, repo_no_commit, mock_session
    ):
        """Uses flush instead of commit when batching operations."""
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )
        repo_no_commit.create_account("new-restaurant")
        mock_session.flush.assert_called_once()
        mock_session.commit.assert_not_called()

    def test_create_account_rolls_back_on_error(self, repo, mock_session):
        """Failed creation leaves DB clean."""
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = (
            []
        )
        mock_session.add.side_effect = SQLAlchemyError("insert failed")
        with pytest.raises(SQLAlchemyError):
            repo.create_account("new-restaurant")
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# TestAccountUpdate — Settings changes with optimistic locking
# ---------------------------------------------------------------------------


class TestAccountUpdate:
    """Account settings changes. Optimistic locking prevents concurrent admin
    edits from silently overwriting each other."""

    def test_update_account_success(self, repo, mock_session, sample_account):
        """Admin updates restaurant display name."""
        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            sample_account
        )
        result = repo.update_account("test-restaurant", display_name="Updated Name")
        assert result == sample_account
        mock_session.commit.assert_called_once()

    def test_update_account_returns_none_when_not_found(self, repo, mock_session):
        """Updating nonexistent account handled gracefully."""
        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            None
        )
        result = repo.update_account("nonexistent", display_name="X")
        assert result is None

    def test_update_account_version_check_passes(
        self, repo, mock_session, sample_account
    ):
        """Optimistic lock succeeds when no concurrent edit."""
        expected_version = int(sample_account.updated_at.timestamp())
        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            sample_account
        )
        result = repo.update_account(
            "test-restaurant",
            expected_version=expected_version,
            display_name="Updated",
        )
        assert result == sample_account

    def test_update_account_version_mismatch_raises_error(
        self, repo, mock_session, sample_account
    ):
        """Concurrent edit detected — prevents data loss."""
        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            sample_account
        )
        wrong_version = int(sample_account.updated_at.timestamp()) + 100
        with pytest.raises(ValueError, match="Version mismatch"):
            repo.update_account(
                "test-restaurant",
                expected_version=wrong_version,
                display_name="Overwrite",
            )

    def test_update_account_can_set_fields_to_none(
        self, repo, mock_session, sample_account
    ):
        """Explicit None clears the field (useful for optional fields)."""
        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            sample_account
        )
        repo.update_account("test-restaurant", display_name=None)
        assert sample_account.display_name is None

    def test_update_account_rolls_back_on_db_error(
        self, repo, mock_session, sample_account
    ):
        """DB failure does not corrupt state."""
        mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
            sample_account
        )
        mock_session.commit.side_effect = SQLAlchemyError("commit failed")
        with pytest.raises(SQLAlchemyError):
            repo.update_account("test-restaurant", display_name="Fail")
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# TestAccountDeletion — Offboarding
# ---------------------------------------------------------------------------


class TestAccountDeletion:
    """Account offboarding. Soft delete preserves data for audit/billing.
    Hard delete cascades correctly to avoid orphan records."""

    def test_soft_delete_sets_status_to_deleted(
        self, repo, mock_session, sample_account
    ):
        """Restaurant cancels but data preserved for billing reconciliation."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_account
        )
        result = repo.delete_account("test-restaurant", hard_delete=False)
        assert sample_account.status == AccountStatus.deleted
        assert result == sample_account
        mock_session.commit.assert_called_once()

    def test_hard_delete_cascades_all_dependent_records(
        self, repo, mock_session, sample_account
    ):
        """Full removal of restaurant and all dependent data."""
        user1_id = uuid.uuid4()
        conv1_id = uuid.uuid4()

        user_row = MagicMock()
        user_row.id = user1_id
        conv_row = MagicMock()
        conv_row.id = conv1_id

        def query_side_effect(model):
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.delete.return_value = None
            if model is User.id:
                mock_q.filter.return_value.all.return_value = [user_row]
            elif model is Conversation.id:
                mock_q.filter.return_value.all.return_value = [conv_row]
            else:
                mock_q.filter.return_value.delete.return_value = None
                mock_q.first.return_value = sample_account
                mock_q.filter.return_value.first.return_value = sample_account
            return mock_q

        mock_session.query.side_effect = query_side_effect

        result = repo.delete_account("test-restaurant", hard_delete=True)
        assert result == sample_account
        mock_session.commit.assert_called_once()

    def test_hard_delete_handles_account_with_no_users(
        self, repo, mock_session, sample_account
    ):
        """Edge case: new account with no activity yet."""

        def query_side_effect(model):
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.delete.return_value = None
            if model is User.id:
                mock_q.filter.return_value.all.return_value = []  # No users
            else:
                mock_q.first.return_value = sample_account
                mock_q.filter.return_value.first.return_value = sample_account
                mock_q.filter.return_value.delete.return_value = None
            return mock_q

        mock_session.query.side_effect = query_side_effect

        result = repo.delete_account("test-restaurant", hard_delete=True)
        assert result == sample_account

    def test_delete_nonexistent_account_returns_none(self, repo, mock_session):
        """No-op when account does not exist."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        result = repo.delete_account("nonexistent", hard_delete=False)
        assert result is None

    def test_delete_rolls_back_on_db_error(self, repo, mock_session, sample_account):
        """Partial cascade failure rolls back cleanly."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_account
        )
        mock_session.commit.side_effect = SQLAlchemyError("cascade error")
        with pytest.raises(SQLAlchemyError):
            repo.delete_account("test-restaurant", hard_delete=False)
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# TestAccountFiltering — Admin dashboard
# ---------------------------------------------------------------------------


class TestAccountFiltering:
    """Admin dashboard for managing all restaurant accounts. Pagination,
    keyword search, and status/subscription filtering."""

    def test_filter_accounts_returns_accounts_and_count(
        self, repo, mock_session, sample_account
    ):
        """Basic filter returns tuple of (accounts, total_count)."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.count.return_value = 1
        mock_q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            sample_account
        ]

        accounts, total = repo.filter_accounts()
        assert accounts == [sample_account]
        assert total == 1

    def test_filter_accounts_with_pagination(self, repo, mock_session, sample_account):
        """Large account list paginated for dashboard."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.count.return_value = 50
        mock_q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            sample_account
        ]

        accounts, total = repo.filter_accounts(page=3, page_size=10)
        assert total == 50

    def test_filter_accounts_by_status(self, repo, mock_session, sample_account):
        """Filter active vs pending accounts."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.count.return_value = 5
        mock_q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            sample_account
        ]

        accounts, total = repo.filter_accounts(status=[AccountStatus.active])
        assert total == 5

    def test_filter_accounts_by_keyword(self, repo, mock_session, sample_account):
        """Admin searches for restaurant by name (case-insensitive)."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.count.return_value = 1
        mock_q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            sample_account
        ]

        accounts, total = repo.filter_accounts(keyword="test")
        assert total == 1

    def test_filter_accounts_by_subscription_status(
        self, repo, mock_session, sample_account
    ):
        """Filter accounts by subscription status uses EXISTS subquery."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.count.return_value = 1
        mock_q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            sample_account
        ]

        accounts, total = repo.filter_accounts(
            subscription_status=[SubscriptionStatus.active]
        )
        assert accounts == [sample_account]
        assert total == 1

    def test_filter_accounts_returns_empty_on_error(self, repo, mock_session):
        """Graceful degradation on DB error."""
        mock_session.query.side_effect = SQLAlchemyError("timeout")
        accounts, total = repo.filter_accounts()
        assert accounts == []
        assert total == 0
        mock_session.rollback.assert_called_once()

    def test_filter_accounts_by_name_returns_list(
        self, repo, mock_session, sample_account
    ):
        """filter_accounts_by_name returns list of matching accounts."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [sample_account]

        result = repo.filter_accounts_by_name(keyword="test")
        assert result == [sample_account]

    def test_filter_accounts_by_name_no_keyword_returns_all(
        self, repo, mock_session, sample_account
    ):
        """No keyword returns all non-deleted accounts."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.all.return_value = [sample_account]

        result = repo.filter_accounts_by_name()
        assert result == [sample_account]

    def test_filter_accounts_by_name_returns_empty_on_error(self, repo, mock_session):
        """Error returns empty list, not crash."""
        mock_session.query.side_effect = SQLAlchemyError("timeout")
        result = repo.filter_accounts_by_name(keyword="x")
        assert result == []

    def test_get_accounts_with_coupons(self, repo, mock_session, sample_account):
        """Billing: identify accounts with active discount coupons."""
        sample_account.stripe_coupon_id = "coupon_123"
        mock_session.query.return_value.filter.return_value.filter.return_value.all.return_value = [
            sample_account
        ]
        result = repo.get_accounts_with_coupons()
        assert len(result) == 1
        assert result[0].stripe_coupon_id == "coupon_123"

    def test_get_accounts_with_coupons_returns_empty_on_error(self, repo, mock_session):
        """Error resilience for billing queries."""
        mock_session.query.return_value.filter.return_value.filter.return_value.all.side_effect = SQLAlchemyError(
            "error"
        )
        result = repo.get_accounts_with_coupons()
        assert result == []


# ---------------------------------------------------------------------------
# TestAccountRepositoryAsync — Real-time request path
# ---------------------------------------------------------------------------


class TestAccountRepositoryAsync:
    """Async variant used in real-time request paths (agent system)."""

    @pytest.mark.asyncio
    async def test_async_get_account_by_name_returns_account(
        self, async_repo, mock_async_session, sample_account
    ):
        """Async tenant resolution during live call."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_account
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_account("test-restaurant")
        assert result == sample_account
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_get_account_by_name_returns_none_when_not_found(
        self, async_repo, mock_async_session
    ):
        """Unknown account name returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_account("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_async_get_account_by_id_returns_account(
        self, async_repo, mock_async_session, sample_account, sample_account_id
    ):
        """Async ID lookup for agent system."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_account
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_account_by_id(sample_account_id)
        assert result == sample_account

    @pytest.mark.asyncio
    async def test_async_get_account_by_stripe_customer_id(
        self, async_repo, mock_async_session, sample_account
    ):
        """Stripe webhook processing finds account."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_account
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_account_by_stripe_customer_id("cus_123")
        assert result == sample_account

    @pytest.mark.asyncio
    async def test_async_get_account_rolls_back_on_error(
        self, async_repo, mock_async_session
    ):
        """Error resilience in async path."""
        mock_async_session.execute.side_effect = SQLAlchemyError("connection lost")

        result = await async_repo.get_account("test")
        assert result is None
        mock_async_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_get_account_by_id_rolls_back_on_error(
        self, async_repo, mock_async_session
    ):
        """Async ID lookup error resilience."""
        mock_async_session.execute.side_effect = SQLAlchemyError("timeout")

        result = await async_repo.get_account_by_id(uuid.uuid4())
        assert result is None
        mock_async_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestGetAllAccountNames — Account name listing for dropdowns
# ---------------------------------------------------------------------------


class TestGetAllAccountNames:
    @pytest.mark.asyncio
    async def test_returns_sorted_account_tuples(self, async_repo, mock_async_session):
        """Returns list of (name, display_name) tuples from the database."""
        mock_result = MagicMock()
        mock_tuples = MagicMock()
        mock_tuples.all.return_value = [
            ("acme", "Acme Corp"),
            ("bravo", None),
            ("charlie", "Charlie's Diner"),
        ]
        mock_result.tuples.return_value = mock_tuples
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_all_account_names()
        assert result == [
            ("acme", "Acme Corp"),
            ("bravo", None),
            ("charlie", "Charlie's Diner"),
        ]

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_error(self, async_repo, mock_async_session):
        """Returns empty list and rolls back on DB error."""
        mock_async_session.execute.side_effect = SQLAlchemyError("connection lost")

        result = await async_repo.get_all_account_names()
        assert result == []
        mock_async_session.rollback.assert_awaited_once()
