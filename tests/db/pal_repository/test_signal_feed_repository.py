"""Tests for db.pal_repository.SignalFeedRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only SignalFeedData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.signal_feed import SignalFeedData
from db.pal_repository.signal_feed import SignalFeedRepository
from db.tables.signal_feeds import SignalFeed

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> SignalFeedRepository:
    return SignalFeedRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_source_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_source_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=SignalFeed)
    row.id = sample_id
    row.source_id = sample_source_id
    feed_type_mock = MagicMock()
    feed_type_mock.value = "image_snapshot"
    row.feed_type = feed_type_mock
    capture_mode_mock = MagicMock()
    capture_mode_mock.value = "pull"
    row.capture_mode = capture_mode_mock
    status_mock = MagicMock()
    status_mock.value = "active"
    row.status = status_mock
    row.status_message = None
    row.last_capture_at = None
    row.last_capture_url = None
    row.capture_count = 0
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = None
    return row


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    """Lookup by primary key."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: SignalFeedRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, SignalFeedData)
        assert data.id == sample_id
        assert data.feed_type == "image_snapshot"
        assert data.capture_mode == "pull"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: SignalFeedRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: SignalFeedRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListBySourceId
# ---------------------------------------------------------------------------


class TestListBySourceId:
    """List feeds for a source."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: SignalFeedRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_source_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_source_id(sample_source_id)

        assert len(results) == 1
        assert isinstance(results[0], SignalFeedData)
        assert results[0].source_id == sample_source_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: SignalFeedRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_source_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: SignalFeedRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("timeout")

        with pytest.raises(RuntimeError, match="timeout"):
            await repo.list_by_source_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByStatus
# ---------------------------------------------------------------------------


class TestListByStatus:
    """List feeds by status."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: SignalFeedRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_status("active")

        assert len(results) == 1
        assert isinstance(results[0], SignalFeedData)
        assert results[0].status == "active"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: SignalFeedRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_status("paused")
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: SignalFeedRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("error")

        with pytest.raises(RuntimeError, match="error"):
            await repo.list_by_status("active")


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new signal feed."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: SignalFeedRepository,
        mock_session: AsyncMock,
        sample_source_id: uuid.UUID,
    ) -> None:
        input_data = SignalFeedData(
            id=uuid.uuid4(),
            source_id=sample_source_id,
            feed_type="image_snapshot",
            capture_mode="pull",
            status="active",
            capture_count=0,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: SignalFeedRepository,
        mock_session: AsyncMock,
        sample_source_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = RuntimeError("insert failed")

        input_data = SignalFeedData(
            id=uuid.uuid4(),
            source_id=sample_source_id,
            feed_type="image_snapshot",
            capture_mode="pull",
            status="active",
            capture_count=0,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(RuntimeError, match="insert failed"):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a signal feed by ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: SignalFeedRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_id)

        assert isinstance(data, SignalFeedData)
        assert data.id == sample_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: SignalFeedRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: SignalFeedRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = RuntimeError("delete failed")

        with pytest.raises(RuntimeError, match="delete failed"):
            await repo.delete(sample_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """SignalFeedData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = SignalFeedData(
            id=uuid.uuid4(),
            source_id=uuid.uuid4(),
            feed_type="image_snapshot",
            capture_mode="pull",
            status="active",
            capture_count=0,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.status = "changed"  # type: ignore[misc]
