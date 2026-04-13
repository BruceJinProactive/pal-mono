"""Tests for ToolCallRecordRepositoryAsync.

Business focus: Tool call failure tracking for agent debugging, evaluator
metrics, and cross-container persistence.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.tool_call_record_repository import ToolCallRecordRepositoryAsync
from db.tables import ToolCallRecord


@pytest.fixture
def mock_async_session():
    session = AsyncMock()
    # AsyncSession.add() is synchronous, not async
    session.add = MagicMock()
    return session


@pytest.fixture
def async_repo(mock_async_session):
    return ToolCallRecordRepositoryAsync(mock_async_session)


@pytest.fixture
def sample_conversation_id():
    return uuid.uuid4()


@pytest.fixture
def sample_tool_call_record():
    record = MagicMock(spec=ToolCallRecord)
    record.id = uuid.uuid4()
    record.conversation_id = uuid.uuid4()
    record.tool_name = "get_restaurant_menu"
    record.is_error = False
    record.error_type = None
    record.duration_ms = 250
    record.result = "Menu retrieved successfully"
    record.created_at = datetime(2025, 3, 1, tzinfo=timezone.utc)
    return record


class TestAddToolCallRecord:
    """Test adding tool call records (fire-and-forget pattern)."""

    @pytest.mark.asyncio
    async def test_add_tool_call_record_success(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Create a tool call record with all fields."""
        mock_record = MagicMock(spec=ToolCallRecord)
        mock_record.id = uuid.uuid4()
        mock_async_session.add.return_value = None
        mock_async_session.commit.return_value = None
        mock_async_session.refresh.return_value = None

        # Capture the record that was added
        def capture_add(record):
            mock_record.conversation_id = record.conversation_id
            mock_record.tool_name = record.tool_name
            mock_record.is_error = record.is_error
            mock_record.error_type = record.error_type
            mock_record.duration_ms = record.duration_ms
            mock_record.result = record.result

        mock_async_session.add.side_effect = capture_add
        mock_async_session.refresh.side_effect = lambda r: setattr(
            r, "id", mock_record.id
        )

        result = await async_repo.add_tool_call_record(
            conversation_id=sample_conversation_id,
            tool_name="create_order",
            is_error=False,
            duration_ms=150,
            result="Order created",
        )

        assert result is not None
        assert result.conversation_id == sample_conversation_id
        assert result.tool_name == "create_order"
        assert result.is_error is False
        assert result.duration_ms == 150
        assert result.result == "Order created"
        mock_async_session.add.assert_called_once()
        mock_async_session.commit.assert_awaited_once()
        mock_async_session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_tool_call_record_with_error(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Record a tool call that failed."""
        mock_record = MagicMock(spec=ToolCallRecord)
        mock_record.id = uuid.uuid4()
        mock_async_session.add.return_value = None
        mock_async_session.commit.return_value = None
        mock_async_session.refresh.return_value = None

        def capture_add(record):
            mock_record.conversation_id = record.conversation_id
            mock_record.tool_name = record.tool_name
            mock_record.is_error = record.is_error
            mock_record.error_type = record.error_type
            mock_record.duration_ms = record.duration_ms
            mock_record.result = record.result

        mock_async_session.add.side_effect = capture_add
        mock_async_session.refresh.side_effect = lambda r: setattr(
            r, "id", mock_record.id
        )

        result = await async_repo.add_tool_call_record(
            conversation_id=sample_conversation_id,
            tool_name="call_external_api",
            is_error=True,
            error_type="APIError",
            duration_ms=5000,
            result="Connection timeout after 5s",
        )

        assert result is not None
        assert result.is_error is True
        assert result.error_type == "APIError"
        assert result.result == "Connection timeout after 5s"

    @pytest.mark.asyncio
    async def test_add_tool_call_record_minimal_fields(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Record with only required fields (no error, no duration, no result)."""
        mock_record = MagicMock(spec=ToolCallRecord)
        mock_record.id = uuid.uuid4()
        mock_async_session.add.return_value = None
        mock_async_session.commit.return_value = None
        mock_async_session.refresh.return_value = None

        def capture_add(record):
            mock_record.conversation_id = record.conversation_id
            mock_record.tool_name = record.tool_name
            mock_record.is_error = record.is_error
            mock_record.error_type = record.error_type
            mock_record.duration_ms = record.duration_ms
            mock_record.result = record.result

        mock_async_session.add.side_effect = capture_add
        mock_async_session.refresh.side_effect = lambda r: setattr(
            r, "id", mock_record.id
        )

        result = await async_repo.add_tool_call_record(
            conversation_id=sample_conversation_id,
            tool_name="simple_tool",
            is_error=False,
        )

        assert result is not None
        assert result.tool_name == "simple_tool"
        assert result.error_type is None
        assert result.duration_ms is None
        assert result.result is None

    @pytest.mark.asyncio
    async def test_add_tool_call_record_returns_none_on_error(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Fire-and-forget: returns None on DB error."""
        mock_async_session.add.return_value = None
        mock_async_session.commit.side_effect = SQLAlchemyError("DB error")

        result = await async_repo.add_tool_call_record(
            conversation_id=sample_conversation_id,
            tool_name="failing_tool",
            is_error=False,
        )

        assert result is None
        mock_async_session.rollback.assert_awaited_once()


class TestGetToolCallsByConversation:
    """Test retrieving tool call records for a conversation."""

    @pytest.mark.asyncio
    async def test_get_tool_calls_returns_ordered_list(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Retrieve all tool calls for a conversation, ordered by created_at."""
        record1 = MagicMock(spec=ToolCallRecord)
        record1.id = uuid.uuid4()
        record1.conversation_id = sample_conversation_id
        record1.tool_name = "first_tool"
        record1.created_at = datetime(2025, 3, 1, 10, 0, 0, tzinfo=timezone.utc)

        record2 = MagicMock(spec=ToolCallRecord)
        record2.id = uuid.uuid4()
        record2.conversation_id = sample_conversation_id
        record2.tool_name = "second_tool"
        record2.created_at = datetime(2025, 3, 1, 10, 5, 0, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [record1, record2]
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_tool_calls_by_conversation(sample_conversation_id)

        assert len(result) == 2
        assert result[0].tool_name == "first_tool"
        assert result[1].tool_name == "second_tool"

    @pytest.mark.asyncio
    async def test_get_tool_calls_returns_empty_list_when_no_records(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Conversation with no tool calls returns empty list."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_tool_calls_by_conversation(sample_conversation_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_tool_calls_returns_empty_list_on_error(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Graceful failure on DB error."""
        mock_async_session.execute.side_effect = SQLAlchemyError("DB error")

        result = await async_repo.get_tool_calls_by_conversation(sample_conversation_id)

        assert result == []
        mock_async_session.rollback.assert_awaited_once()


class TestMultipleToolCallsPerConversation:
    """Test scenarios with multiple tool calls for the same conversation."""

    @pytest.mark.asyncio
    async def test_multiple_records_same_conversation(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Multiple tool calls for same conversation are retrieved correctly."""
        records = [
            MagicMock(
                spec=ToolCallRecord,
                id=uuid.uuid4(),
                conversation_id=sample_conversation_id,
                tool_name=f"tool_{i}",
                is_error=False,
                created_at=datetime(2025, 3, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(5)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = records
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_tool_calls_by_conversation(sample_conversation_id)

        assert len(result) == 5
        for i, record in enumerate(result):
            assert record.tool_name == f"tool_{i}"


class TestResultTruncation:
    """Test that result strings longer than 1000 characters are truncated."""

    @pytest.mark.asyncio
    async def test_result_truncated_to_1000_chars(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Result strings longer than 1000 characters are truncated."""
        mock_record = MagicMock(spec=ToolCallRecord)
        mock_record.id = uuid.uuid4()
        mock_async_session.commit.return_value = None
        mock_async_session.refresh.return_value = None

        long_result = "x" * 1500  # 1500 characters

        def capture_add(record):
            mock_record.conversation_id = record.conversation_id
            mock_record.tool_name = record.tool_name
            mock_record.result = record.result

        mock_async_session.add.side_effect = capture_add
        mock_async_session.refresh.side_effect = lambda r: setattr(
            r, "id", mock_record.id
        )

        result = await async_repo.add_tool_call_record(
            conversation_id=sample_conversation_id,
            tool_name="long_output_tool",
            is_error=False,
            result=long_result,
        )

        assert result is not None
        assert len(result.result) == 1000
        assert result.result == "x" * 1000

    @pytest.mark.asyncio
    async def test_result_under_1000_chars_unchanged(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Result strings shorter than 1000 characters pass through unchanged."""
        mock_record = MagicMock(spec=ToolCallRecord)
        mock_record.id = uuid.uuid4()
        mock_async_session.commit.return_value = None
        mock_async_session.refresh.return_value = None

        short_result = "x" * 500  # 500 characters

        def capture_add(record):
            mock_record.conversation_id = record.conversation_id
            mock_record.tool_name = record.tool_name
            mock_record.result = record.result

        mock_async_session.add.side_effect = capture_add
        mock_async_session.refresh.side_effect = lambda r: setattr(
            r, "id", mock_record.id
        )

        result = await async_repo.add_tool_call_record(
            conversation_id=sample_conversation_id,
            tool_name="short_output_tool",
            is_error=False,
            result=short_result,
        )

        assert result is not None
        assert len(result.result) == 500
        assert result.result == short_result
