"""Tests for db.pal_repository.FeedbackRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.feedback import FeedbackData
from db.pal_repository.feedback import FeedbackRepository


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> FeedbackRepository:
    return FeedbackRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_message_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID, sample_message_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = sample_id
    row.message_id = sample_message_id
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.author_identifier = "user_abc"
    row.author_name = "Alice"
    row.reaction = "thumbs_up"
    row.tags = ["helpful", "accurate"]
    row.note = "Great response"
    return row


class TestGetById:

    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: FeedbackRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_id(sample_id)
        assert isinstance(data, FeedbackData)
        assert data.id == sample_id
        assert data.reaction == "thumbs_up"
        assert data.tags == ("helpful", "accurate")

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: FeedbackRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: FeedbackRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestGetByMessageIds:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: FeedbackRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_message_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_message_ids([sample_message_id])
        assert len(results) == 1
        assert results[0].message_id == sample_message_id
        assert results[0].author_name == "Alice"

    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_input(
        self, repo: FeedbackRepository, mock_session: AsyncMock
    ) -> None:
        results = await repo.get_by_message_ids([])
        assert results == []
        mock_session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: FeedbackRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_message_ids([uuid.uuid4()])
        mock_session.rollback.assert_awaited_once()


class TestCreate:

    @pytest.mark.asyncio
    async def test_creates_and_returns_data(
        self,
        repo: FeedbackRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(return_value=None)

        async def fake_refresh(row: MagicMock) -> None:
            row.id = sample_orm_row.id
            row.message_id = sample_orm_row.message_id
            row.created_at = sample_orm_row.created_at
            row.updated_at = sample_orm_row.updated_at
            row.author_identifier = sample_orm_row.author_identifier
            row.author_name = sample_orm_row.author_name
            row.reaction = sample_orm_row.reaction
            row.tags = sample_orm_row.tags
            row.note = sample_orm_row.note

        mock_session.refresh.side_effect = fake_refresh

        record = FeedbackData(
            id=uuid.uuid4(),
            message_id=sample_orm_row.message_id,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            author_identifier="user_abc",
            author_name="Alice",
            reaction="thumbs_up",
            tags=("helpful", "accurate"),
            note="Great response",
        )
        data = await repo.create(record)
        assert isinstance(data, FeedbackData)
        assert data.reaction == "thumbs_up"
        assert data.tags == ("helpful", "accurate")
        mock_session.commit.assert_awaited_once()
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: FeedbackRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.commit.side_effect = RuntimeError("db error")
        mock_session.rollback = AsyncMock(return_value=None)
        record = FeedbackData(
            id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(RuntimeError, match="db error"):
            await repo.create(record)
        mock_session.rollback.assert_awaited_once()


class TestDelete:

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: FeedbackRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock(return_value=None)
        mock_session.delete = AsyncMock(return_value=None)
        data = await repo.delete(sample_id)
        assert isinstance(data, FeedbackData)
        assert data.id == sample_id
        mock_session.delete.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: FeedbackRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        assert await repo.delete(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: FeedbackRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.delete(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:

    def test_session_stored(
        self, repo: FeedbackRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self) -> None:
        data = FeedbackData(
            id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            reaction="thumbs_up",
            tags=("helpful",),
        )
        with pytest.raises(AttributeError):
            data.reaction = "thumbs_down"  # type: ignore[misc]

    def test_tags_coerced_to_tuple(self) -> None:
        data = FeedbackData(
            id=uuid.uuid4(),
            message_id=uuid.uuid4(),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tags=["a", "b"],  # type: ignore[arg-type]
        )
        assert isinstance(data.tags, tuple)
        assert data.tags == ("a", "b")
