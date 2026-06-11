"""Tests for ConversationRepository and ConversationRepositoryAsync.

Business focus: Analytics filtering, JSONB escalation flag, dashboard counts,
conversation lifecycle, and session management.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.conversation_repository import (
    ConversationRepository,
    ConversationRepositoryAsync,
    ConversationUpdate,
    _split_call_purpose_values,
)
from db.tables import Conversation, ConversationStatus

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
    mock_query.join.return_value = mock_query
    mock_query.group_by.return_value = mock_query
    mock_query.having.return_value = mock_query
    return session


@pytest.fixture
def mock_async_session():
    return AsyncMock()


@pytest.fixture
def repo(mock_session):
    return ConversationRepository(mock_session)


@pytest.fixture
def async_repo(mock_async_session):
    return ConversationRepositoryAsync(mock_async_session)


@pytest.fixture
def sample_conversation_id():
    return uuid.uuid4()


@pytest.fixture
def sample_conversation(sample_conversation_id):
    conv = MagicMock(spec=Conversation)
    conv.id = sample_conversation_id
    conv.user_id = uuid.uuid4()
    conv.project_id = uuid.uuid4()
    conv.status = ConversationStatus.ACTIVE
    conv.language = "english"
    conv.purpose = "ordering"
    conv.ended_reason = None
    conv.is_test = False
    conv.created_at = datetime(2025, 3, 1, tzinfo=timezone.utc)
    return conv


# ---------------------------------------------------------------------------
# TestConversationLookupAsync — Agent retrieves current session
# ---------------------------------------------------------------------------


class TestConversationLookupAsync:
    """Session lookup used by the agent system during live interactions."""

    @pytest.mark.asyncio
    async def test_get_conversation_by_id_returns_conversation(
        self, async_repo, mock_async_session, sample_conversation
    ):
        """Agent retrieves current session."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_conversation_by_id(sample_conversation.id)
        assert result == sample_conversation

    @pytest.mark.asyncio
    async def test_get_conversation_by_id_raises_when_not_found(
        self, async_repo, mock_async_session
    ):
        """Missing conversation raises ValueError (not None)."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="No conversation found"):
            await async_repo.get_conversation_by_id(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_conversation_by_call_id(
        self, async_repo, mock_async_session, sample_conversation
    ):
        """Voice call lookup by call ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_conversation_by_call_id("call_abc123")
        assert result == sample_conversation

    @pytest.mark.asyncio
    async def test_get_conversation_by_call_id_returns_none_on_error(
        self, async_repo, mock_async_session
    ):
        """Graceful failure on DB error."""
        mock_async_session.execute.side_effect = SQLAlchemyError("error")

        result = await async_repo.get_conversation_by_call_id("call_abc")
        assert result is None
        mock_async_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_open_conversations_by_user_and_project(
        self, async_repo, mock_async_session, sample_conversation
    ):
        """Find active sessions for SMS conversation reuse."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_conversation]
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_open_conversations_by_user_and_project(
            user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
        assert result == [sample_conversation]

    @pytest.mark.asyncio
    async def test_get_by_project_returns_conversations(
        self, async_repo, mock_async_session, sample_conversation
    ):
        """Retrieve recent conversations for a project."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_conversation]
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_by_project(sample_conversation.project_id)
        assert result == [sample_conversation]

    @pytest.mark.asyncio
    async def test_get_by_project_returns_empty_on_error(
        self, async_repo, mock_async_session
    ):
        """DB error returns empty list."""
        mock_async_session.execute.side_effect = SQLAlchemyError("error")

        result = await async_repo.get_by_project(uuid.uuid4())
        assert result == []
        mock_async_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_count_conversations_by_account(self, async_repo, mock_async_session):
        """Dashboard metric: total sessions for account."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.count_conversations_by_account_id(uuid.uuid4())
        assert result == 42

    @pytest.mark.asyncio
    async def test_count_conversations_returns_zero_when_none(
        self, async_repo, mock_async_session
    ):
        """No conversations returns 0."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.count_conversations_by_account_id(uuid.uuid4())
        assert result == 0


# ---------------------------------------------------------------------------
# TestConversationUpdateAsync — Status, escalation, classification
# ---------------------------------------------------------------------------


class TestConversationUpdateAsync:
    """Conversation field updates including JSONB escalation flag propagation."""

    @pytest.mark.asyncio
    async def test_update_conversation_status(
        self, async_repo, mock_async_session, sample_conversation
    ):
        """Agent marks conversation completed."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_async_session.execute.return_value = mock_result

        update = ConversationUpdate(status=ConversationStatus.CLOSED)
        await async_repo.update_conversation(sample_conversation.id, update)
        assert sample_conversation.status == ConversationStatus.CLOSED
        mock_async_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_conversation_purpose_and_language(
        self, async_repo, mock_async_session, sample_conversation
    ):
        """Agent classifies call purpose during conversation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_async_session.execute.return_value = mock_result

        update = ConversationUpdate(purpose="reservation", language="spanish")
        await async_repo.update_conversation(sample_conversation.id, update)
        assert sample_conversation.purpose == "reservation"
        assert sample_conversation.language == "spanish"

    @pytest.mark.asyncio
    async def test_update_escalation_flag_executes_jsonb_update(
        self, async_repo, mock_async_session, sample_conversation
    ):
        """Escalation flag set via JSONB update on all messages."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_async_session.execute.return_value = mock_result

        update = ConversationUpdate(is_escalated=True)
        await async_repo.update_conversation(sample_conversation.id, update)
        # execute called twice: once for get_by_id, once for the JSONB update
        assert mock_async_session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_update_nonexistent_conversation_raises(
        self, async_repo, mock_async_session
    ):
        """get_conversation_by_id raises ValueError, not returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_async_session.execute.return_value = mock_result

        update = ConversationUpdate(status=ConversationStatus.CLOSED)
        with pytest.raises(ValueError, match="No conversation found"):
            await async_repo.update_conversation(uuid.uuid4(), update)

    @pytest.mark.asyncio
    async def test_update_rolls_back_on_db_error(
        self, async_repo, mock_async_session, sample_conversation
    ):
        """Failed update cleans up session."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_async_session.execute.return_value = mock_result
        mock_async_session.commit.side_effect = SQLAlchemyError("commit error")

        update = ConversationUpdate(status=ConversationStatus.CLOSED)
        with pytest.raises(SQLAlchemyError):
            await async_repo.update_conversation(sample_conversation.id, update)
        mock_async_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestConversationFiltering — Analytics queries
# ---------------------------------------------------------------------------


class TestConversationFiltering:
    """Analytics filters must compose correctly for dashboard reporting."""

    def test_split_call_purpose_values_returns_first_level_tokens(self):
        """Purpose filters accept historical comma-separated combinations."""
        assert _split_call_purpose_values(
            [
                "customer_service,dietary_specific,store_info",
                "store_info",
                "ordering",
            ]
        ) == [
            "customer_service",
            "dietary_specific",
            "store_info",
            "ordering",
        ]

    def test_get_conversation_ids_with_date_range(
        self, repo, mock_session, sample_conversation_id
    ):
        """Analytics: filter sessions by date."""
        mock_session.query.return_value.filter.return_value.all.return_value = [
            (sample_conversation_id,)
        ]
        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )
        assert result == [sample_conversation_id]

    def test_get_conversation_ids_with_language_filter(
        self, repo, mock_session, sample_conversation_id
    ):
        """Analytics: Spanish-only sessions."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            language=["spanish"],
        )
        assert result == [sample_conversation_id]

    def test_get_conversation_ids_with_purpose_filter(
        self, repo, mock_session, sample_conversation_id
    ):
        """Analytics: selected purposes match any purpose token on the call."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            purpose=["ordering"],
        )
        assert result == [sample_conversation_id]

        compiled_filters = [
            str(call.args[0].compile(dialect=postgresql.dialect()))
            for call in mock_q.filter.call_args_list
        ]
        assert any(
            "string_to_array" in compiled_filter and "&&" in compiled_filter
            for compiled_filter in compiled_filters
        )

    def test_get_conversation_ids_with_ended_reason_filter(
        self, repo, mock_session, sample_conversation_id
    ):
        """Analytics: identify dropped calls."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            ended_reason=["customer_ended"],
        )
        assert result == [sample_conversation_id]

    def test_get_conversation_ids_hide_testing_sessions(
        self, repo, mock_session, sample_conversation_id
    ):
        """Exclude test calls from production analytics."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            hide_testing_sessions=True,
        )
        assert result == [sample_conversation_id]

    def test_get_conversation_ids_with_customer_converted_true(
        self, repo, mock_session, sample_conversation_id
    ):
        """Track conversion attribution."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            customer_converted=True,
        )
        assert result == [sample_conversation_id]

    def test_get_conversation_ids_with_customer_not_converted(
        self, repo, mock_session, sample_conversation_id
    ):
        """Identify unconverted sessions."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            customer_converted=False,
        )
        assert result == [sample_conversation_id]

    def test_get_conversation_ids_with_orders_filter(
        self, repo, mock_session, sample_conversation_id
    ) -> None:
        """Admin console can list only conversations with stored orders."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            has_order=True,
        )

        assert result == [sample_conversation_id]
        compiled_filters = [
            str(call.args[0].compile(dialect=postgresql.dialect()))
            for call in mock_q.filter.call_args_list
        ]
        assert any(
            "conversations.id IN" in compiled_filter
            and "orders.conversation_id" in compiled_filter
            for compiled_filter in compiled_filters
        )

    def test_get_conversation_ids_without_orders_filter(
        self, repo, mock_session, sample_conversation_id
    ) -> None:
        """Admin console can list only conversations without stored orders."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            has_order=False,
        )

        assert result == [sample_conversation_id]
        compiled_filters = [
            str(call.args[0].compile(dialect=postgresql.dialect()))
            for call in mock_q.filter.call_args_list
        ]
        assert any(
            "conversations.id NOT IN" in compiled_filter
            and "orders.conversation_id" in compiled_filter
            for compiled_filter in compiled_filters
        )

    def test_get_conversation_ids_all_order_filter(
        self, repo, mock_session, sample_conversation_id
    ) -> None:
        """Admin console can list conversations with any stored order."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            order_filter="all",
        )

        assert result == [sample_conversation_id]
        compiled_filters = [
            str(call.args[0].compile(dialect=postgresql.dialect()))
            for call in mock_q.filter.call_args_list
        ]
        assert any(
            "conversations.id IN" in compiled_filter
            and "orders.conversation_id" in compiled_filter
            for compiled_filter in compiled_filters
        )

    def test_get_conversation_ids_paid_order_filter(
        self, repo, mock_session, sample_conversation_id
    ) -> None:
        """Admin console can list conversations whose latest order is paid."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            order_filter="paid",
        )

        assert result == [sample_conversation_id]
        assert mock_q.join.called
        compiled_filters = [
            str(call.args[0].compile(dialect=postgresql.dialect()))
            for call in mock_q.filter.call_args_list
        ]
        assert any(
            "lower(trim(coalesce" in compiled_filter and "NOT IN" in compiled_filter
            for compiled_filter in compiled_filters
        )

    def test_get_conversation_ids_unpaid_order_filter(
        self, repo, mock_session, sample_conversation_id
    ) -> None:
        """Admin console can list conversations whose latest order is unpaid."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.all.return_value = [(sample_conversation_id,)]

        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            order_filter="unpaid",
        )

        assert result == [sample_conversation_id]
        assert mock_q.join.called
        compiled_filters = [
            str(call.args[0].compile(dialect=postgresql.dialect()))
            for call in mock_q.filter.call_args_list
        ]
        assert any(
            "lower(trim(coalesce" in compiled_filter
            and " IN " in compiled_filter
            and "NOT IN" not in compiled_filter
            for compiled_filter in compiled_filters
        )

    def test_get_conversation_ids_returns_empty_on_error(self, repo, mock_session):
        """Graceful degradation."""
        mock_session.query.return_value.filter.return_value.all.side_effect = (
            SQLAlchemyError("error")
        )
        result = repo.get_conversation_ids_by_user_ids(
            user_ids=[uuid.uuid4()],
            start_date=None,
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )
        assert result == []
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# TestConversationDistinctFilters — Dashboard filter dropdowns
# ---------------------------------------------------------------------------


class TestConversationDistinctFilters:
    """Dashboard filter dropdowns populated from distinct conversation values."""

    def test_get_distinct_filter_values_returns_all_three(self, repo, mock_session):
        """Dashboard populates filter dropdowns with first-level purposes."""
        mock_q = mock_session.query.return_value
        mock_q.join.return_value.filter.return_value.one.return_value = (
            ["english", "spanish"],
            [
                "customer_service,dietary_specific,store_info",
                "store_info",
                "delivery",
            ],
            ["customer_ended"],
        )

        languages, purposes, ended_reasons = repo.get_distinct_filter_values(
            uuid.uuid4()
        )
        assert languages == ["english", "spanish"]
        assert purposes == [
            "store_info",
            "delivery",
            "customer_service",
            "dietary_specific",
        ]
        assert ended_reasons == ["customer_ended"]

    def test_get_distinct_filter_values_handles_null_arrays(self, repo, mock_session):
        """No data yet returns empty lists."""
        mock_q = mock_session.query.return_value
        mock_q.join.return_value.filter.return_value.one.return_value = (
            None,
            None,
            None,
        )

        languages, purposes, ended_reasons = repo.get_distinct_filter_values(
            uuid.uuid4()
        )
        assert languages == []
        assert purposes == []
        assert ended_reasons == []

    def test_get_distinct_filter_values_returns_empty_on_error(
        self, repo, mock_session
    ):
        """Error gives empty dropdowns, not crash."""
        mock_session.query.side_effect = SQLAlchemyError("error")

        languages, purposes, ended_reasons = repo.get_distinct_filter_values(
            uuid.uuid4()
        )
        assert languages == []
        assert purposes == []
        assert ended_reasons == []


# ---------------------------------------------------------------------------
# TestConversationCounts — Revenue reporting
# ---------------------------------------------------------------------------


class TestConversationCounts:
    """Conversation counts grouped by account feed into revenue reporting."""

    def test_get_counts_for_single_account(
        self, repo, mock_session, sample_conversation
    ):
        """Dashboard shows count for one restaurant."""
        account_id = uuid.uuid4()
        mock_q = mock_session.query.return_value
        mock_q.join.return_value.join.return_value.filter.return_value.filter.return_value.group_by.return_value.all.return_value = [
            (account_id, "restaurant-a", 10)
        ]

        result = repo.get_conversation_counts_by_account(
            account_id=account_id,
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )
        assert len(result) == 1
        assert result[0] == (account_id, "restaurant-a", 10)

    def test_get_counts_for_all_accounts_includes_total_row(self, repo, mock_session):
        """Admin view: all accounts with TOTAL summary."""
        acct1 = uuid.uuid4()
        acct2 = uuid.uuid4()
        mock_q = mock_session.query.return_value
        mock_q.join.return_value.join.return_value.having.return_value.group_by.return_value.all.return_value = [
            (acct1, "restaurant-a", 10),
            (acct2, "restaurant-b", 20),
        ]

        result = repo.get_conversation_counts_by_account()
        # Should have TOTAL row appended
        assert len(result) == 3
        assert result[-1] == (None, "TOTAL", 30)

    def test_get_counts_empty_results_no_total_row(self, repo, mock_session):
        """No data returns empty list (no phantom TOTAL)."""
        mock_q = mock_session.query.return_value
        mock_q.join.return_value.join.return_value.having.return_value.group_by.return_value.all.return_value = (
            []
        )

        result = repo.get_conversation_counts_by_account()
        assert result == []

    def test_get_counts_rolls_back_on_error(self, repo, mock_session):
        """DB error raises after rollback."""
        mock_session.query.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            repo.get_conversation_counts_by_account()
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# TestConversationPagination — Dashboard session list
# ---------------------------------------------------------------------------


class TestConversationPagination:
    """Paginated session lists for the dashboard."""

    def test_get_conversations_by_users_paginated(
        self, repo, mock_session, sample_conversation
    ):
        """Dashboard session list paged."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.count.return_value = 25
        mock_q.order_by.return_value.limit.return_value.offset.return_value.all.return_value = [
            sample_conversation
        ]

        conversations, total = repo.get_conversations_by_users(
            user_ids=[uuid.uuid4()], page=1, page_size=10
        )
        assert conversations == [sample_conversation]
        assert total == 25

    def test_get_conversations_by_users_empty_ids_returns_empty(
        self, repo, mock_session
    ):
        """No users yields empty result."""
        conversations, total = repo.get_conversations_by_users(
            user_ids=[], page=1, page_size=10
        )
        assert conversations == []
        assert total == 0

    def test_get_conversations_by_users_returns_empty_on_error(
        self, repo, mock_session
    ):
        """Graceful degradation on DB error."""
        mock_session.query.return_value.filter.return_value.count.side_effect = (
            SQLAlchemyError("error")
        )
        conversations, total = repo.get_conversations_by_users(
            user_ids=[uuid.uuid4()], page=1, page_size=10
        )
        assert conversations == []
        assert total == 0

    def test_get_paginated_sessions_by_ids(
        self, repo, mock_session, sample_conversation
    ):
        """Paginated session detail view."""
        mock_q = (
            mock_session.query.return_value.filter.return_value.order_by.return_value
        )
        mock_q.count.return_value = 5
        mock_q.offset.return_value.limit.return_value.all.return_value = [
            sample_conversation
        ]

        count, sessions = repo.get_paginated_sessions_by_ids(
            session_ids=[sample_conversation.id], offset=0, limit=10
        )
        assert count == 5
        assert sessions == [sample_conversation]

    def test_get_paginated_sessions_returns_empty_on_error(self, repo, mock_session):
        """Error returns (0, [])."""
        mock_session.query.side_effect = SQLAlchemyError("error")
        count, sessions = repo.get_paginated_sessions_by_ids(
            session_ids=[uuid.uuid4()], offset=0, limit=10
        )
        assert count == 0
        assert sessions == []

    def test_get_session_count_by_status_and_date(self, repo, mock_session):
        """Session count by status for analytics."""
        mock_q = mock_session.query.return_value.filter.return_value
        mock_q.filter.return_value.count.return_value = 15

        result = repo.get_session_count_by_user_and_status(
            user_ids=[uuid.uuid4()],
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            status=ConversationStatus.ACTIVE,
        )
        assert result == 15

    def test_get_session_count_returns_zero_on_error(self, repo, mock_session):
        """Error returns 0."""
        mock_session.query.return_value.filter.return_value.filter.return_value.count.side_effect = SQLAlchemyError(
            "error"
        )
        result = repo.get_session_count_by_user_and_status(
            user_ids=[uuid.uuid4()],
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
            status=ConversationStatus.ACTIVE,
        )
        assert result == 0


# ---------------------------------------------------------------------------
# TestConversationSync — Basic sync operations
# ---------------------------------------------------------------------------


class TestConversationSync:
    """Sync conversation operations for non-async paths."""

    def test_get_conversations_paginated(self, repo, mock_session, sample_conversation):
        """Basic pagination."""
        mock_session.query.return_value.offset.return_value.limit.return_value.all.return_value = [
            sample_conversation
        ]
        result = repo.get_conversations(skip=0, limit=10)
        assert result == [sample_conversation]

    def test_get_conversations_returns_empty_list_on_error(self, repo, mock_session):
        """Error returns empty list for safe iteration."""
        mock_session.query.return_value.offset.return_value.limit.return_value.all.side_effect = SQLAlchemyError(
            "error"
        )
        result = repo.get_conversations()
        assert result == []

    def test_get_conversations_by_user(self, repo, mock_session, sample_conversation):
        """Retrieve all conversations for a user."""
        mock_session.query.return_value.filter.return_value.all.return_value = [
            sample_conversation
        ]
        result = repo.get_conversations_by_user(uuid.uuid4())
        assert result == [sample_conversation]

    def test_get_conversations_by_user_raises_without_user_id(self, repo):
        """Input validation: user_id required."""
        with pytest.raises(ValueError, match="user_id"):
            repo.get_conversations_by_user(None)

    def test_create_conversation(self, repo, mock_session):
        """Create new conversation for user."""
        repo.create_conversation(uuid.uuid4())
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_create_conversation_returns_none_on_error(self, repo, mock_session):
        """DB error returns None."""
        mock_session.add.side_effect = SQLAlchemyError("error")
        result = repo.create_conversation(uuid.uuid4())
        assert result is None
        mock_session.rollback.assert_called_once()

    def test_sync_get_conversation_by_id(self, repo, mock_session, sample_conversation):
        """Sync path conversation lookup."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_conversation
        )
        result = repo.get_conversation_by_id(sample_conversation.id)
        assert result == sample_conversation

    def test_sync_update_conversation_status(
        self, repo, mock_session, sample_conversation
    ):
        """Sync update sets fields and commits."""
        mock_session.query.return_value.filter.return_value.first.return_value = (
            sample_conversation
        )

        update = ConversationUpdate(status=ConversationStatus.CLOSED)
        repo.update_conversation(sample_conversation.id, update)
        assert sample_conversation.status == ConversationStatus.CLOSED
        mock_session.commit.assert_called_once()

    def test_sync_update_conversation_not_found_returns_none(self, repo, mock_session):
        """Nonexistent conversation returns None."""
        mock_session.query.return_value.filter.return_value.first.return_value = None
        update = ConversationUpdate(status=ConversationStatus.CLOSED)
        result = repo.update_conversation(uuid.uuid4(), update)
        assert result is None
