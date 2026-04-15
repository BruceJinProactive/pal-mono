"""Tests for MessageRepositoryAsync.

Business focus: Message retrieval and conversation management, including
batched pagination for large conversations.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.repositories.message_repository import MessageRepositoryAsync
from db.tables import Message


@pytest.fixture
def mock_async_session():
    session = AsyncMock()
    # AsyncSession.add() is synchronous, not async
    session.add = MagicMock()
    return session


@pytest.fixture
def async_repo(mock_async_session):
    return MessageRepositoryAsync(mock_async_session)


@pytest.fixture
def sample_conversation_id():
    return uuid.uuid4()


def create_mock_message(
    conversation_id: uuid.UUID, body: dict, created_at: datetime
) -> MagicMock:
    """Helper to create a mock Message object."""
    message = MagicMock(spec=Message)
    message.id = uuid.uuid4()
    message.conversation_id = conversation_id
    message.body = body
    message.created_at = created_at
    return message


class TestGetAllMessagesByConversation:
    """Test retrieving all messages for a conversation with pagination."""

    @pytest.mark.asyncio
    async def test_get_all_messages_single_batch(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Retrieve messages when all fit in a single batch."""
        messages = [
            create_mock_message(
                sample_conversation_id,
                {"role": "user", "content": f"Message {i}"},
                datetime(2025, 3, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(5)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = messages
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_all_messages_by_conversation(
            sample_conversation_id, batch_size=100
        )

        assert len(result) == 5
        assert all(msg.conversation_id == sample_conversation_id for msg in result)
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_all_messages_multiple_batches(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Retrieve messages across multiple batches (pagination)."""
        # Create 3 batches: 10 + 10 + 5 = 25 messages
        batch1 = [
            create_mock_message(
                sample_conversation_id,
                {"role": "user", "content": f"Message {i}"},
                datetime(2025, 3, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(10)
        ]
        batch2 = [
            create_mock_message(
                sample_conversation_id,
                {"role": "user", "content": f"Message {i}"},
                datetime(2025, 3, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(10, 20)
        ]
        batch3 = [
            create_mock_message(
                sample_conversation_id,
                {"role": "user", "content": f"Message {i}"},
                datetime(2025, 3, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(20, 25)
        ]

        # Mock execute to return different batches on successive calls
        mock_results = [MagicMock() for _ in range(3)]
        mock_results[0].scalars.return_value.all.return_value = batch1
        mock_results[1].scalars.return_value.all.return_value = batch2
        mock_results[2].scalars.return_value.all.return_value = batch3

        mock_async_session.execute.side_effect = mock_results

        result = await async_repo.get_all_messages_by_conversation(
            sample_conversation_id, batch_size=10
        )

        # Should have retrieved all 25 messages
        assert len(result) == 25
        # Execute should have been called 3 times (3 batches)
        assert mock_async_session.execute.await_count == 3

    @pytest.mark.asyncio
    async def test_get_all_messages_empty_conversation(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Retrieve messages from a conversation with no messages."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_all_messages_by_conversation(
            sample_conversation_id
        )

        assert result == []
        mock_async_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_all_messages_exact_batch_size(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Retrieve messages when count exactly matches batch size."""
        # Exactly 10 messages with batch_size=10
        batch1 = [
            create_mock_message(
                sample_conversation_id,
                {"role": "user", "content": f"Message {i}"},
                datetime(2025, 3, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(10)
        ]

        # First call returns 10, second call returns empty
        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = batch1
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = []

        mock_async_session.execute.side_effect = [mock_result1, mock_result2]

        result = await async_repo.get_all_messages_by_conversation(
            sample_conversation_id, batch_size=10
        )

        # Should retrieve all 10 messages
        assert len(result) == 10
        # Should call execute twice (second call confirms no more data)
        assert mock_async_session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_get_all_messages_partial_final_batch(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Retrieve messages where final batch is partial (stops pagination)."""
        batch1 = [
            create_mock_message(
                sample_conversation_id,
                {"role": "user", "content": f"Message {i}"},
                datetime(2025, 3, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(10)
        ]
        batch2 = [
            create_mock_message(
                sample_conversation_id,
                {"role": "user", "content": f"Message {i}"},
                datetime(2025, 3, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(10, 15)
        ]  # Only 5 messages in final batch

        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = batch1
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = batch2

        mock_async_session.execute.side_effect = [mock_result1, mock_result2]

        result = await async_repo.get_all_messages_by_conversation(
            sample_conversation_id, batch_size=10
        )

        # Should retrieve all 15 messages
        assert len(result) == 15
        # Should stop after second batch (partial batch signals end)
        assert mock_async_session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_get_all_messages_returns_empty_on_error(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Return empty list on database error."""
        mock_async_session.execute.side_effect = SQLAlchemyError("DB connection lost")

        result = await async_repo.get_all_messages_by_conversation(
            sample_conversation_id
        )

        assert result == []
        mock_async_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_all_messages_custom_batch_size(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Use a custom batch size for pagination."""
        batch1 = [
            create_mock_message(
                sample_conversation_id,
                {"role": "user", "content": f"Message {i}"},
                datetime(2025, 3, 1, 10, 0, i, tzinfo=timezone.utc),
            )
            for i in range(50)
        ]
        batch2 = [
            create_mock_message(
                sample_conversation_id,
                {"role": "user", "content": f"Message {i}"},
                datetime(2025, 3, 1, 11, 0, i - 50, tzinfo=timezone.utc),
            )
            for i in range(50, 75)
        ]

        mock_result1 = MagicMock()
        mock_result1.scalars.return_value.all.return_value = batch1
        mock_result2 = MagicMock()
        mock_result2.scalars.return_value.all.return_value = batch2

        mock_async_session.execute.side_effect = [mock_result1, mock_result2]

        result = await async_repo.get_all_messages_by_conversation(
            sample_conversation_id, batch_size=50
        )

        assert len(result) == 75
        assert mock_async_session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_get_all_messages_maintains_chronological_order(
        self, async_repo, mock_async_session, sample_conversation_id
    ):
        """Messages are returned in chronological order (ascending created_at)."""
        messages = [
            create_mock_message(
                sample_conversation_id,
                {"role": "user", "content": f"Message {i}"},
                datetime(2025, 3, 1, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(5)
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = messages
        mock_async_session.execute.return_value = mock_result

        result = await async_repo.get_all_messages_by_conversation(
            sample_conversation_id
        )

        # Verify chronological order
        for i in range(len(result) - 1):
            assert result[i].created_at <= result[i + 1].created_at
