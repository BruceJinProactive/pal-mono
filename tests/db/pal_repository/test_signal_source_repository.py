"""Tests for db.pal_repository.SignalSourceRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only SignalSourceData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.signal_source import SignalSourceData
from db.pal_repository.signal_source import SignalSourceRepository
from db.tables.signal_sources import SignalSource

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> SignalSourceRepository:
    return SignalSourceRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_account_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_account_id: uuid.UUID,
    sample_project_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=SignalSource)
    row.id = sample_id
    row.account_id = sample_account_id
    row.project_id = sample_project_id
    # Use MagicMock for enum fields so .value works
    signal_type_mock = MagicMock()
    signal_type_mock.value = "camera"
    row.signal_type = signal_type_mock
    row.name = "Front Door Camera"
    row.description = "Camera at front entrance"
    status_mock = MagicMock()
    status_mock.value = "active"
    row.status = status_mock
    row.status_message = None
    row.config = {"stream_url": "rtsp://example.com/stream"}
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
        repo: SignalSourceRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, SignalSourceData)
        assert data.id == sample_id
        assert data.signal_type == "camera"
        assert data.name == "Front Door Camera"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: SignalSourceRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: SignalSourceRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        with pytest.raises(Exception):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByAccount
# ---------------------------------------------------------------------------


class TestListByAccount:
    """List all signal sources for an account."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: SignalSourceRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(sample_account_id)

        assert len(results) == 1
        assert isinstance(results[0], SignalSourceData)
        assert results[0].account_id == sample_account_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: SignalSourceRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_filters_by_signal_type(
        self,
        repo: SignalSourceRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account(sample_account_id, signal_type="camera")

        assert len(results) == 1
        assert results[0].signal_type == "camera"

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: SignalSourceRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        with pytest.raises(Exception):
            await repo.list_by_account(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByProject
# ---------------------------------------------------------------------------


class TestListByProject:
    """List all signal sources for a project."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: SignalSourceRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_project(sample_project_id)

        assert len(results) == 1
        assert results[0].project_id == sample_project_id

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: SignalSourceRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        with pytest.raises(Exception):
            await repo.list_by_project(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new signal source."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: SignalSourceRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        input_data = SignalSourceData(
            id=uuid.uuid4(),
            account_id=sample_account_id,
            signal_type="camera",
            name="Test Camera",
            status="active",
            config={"stream_url": "rtsp://example.com"},
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: SignalSourceRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        input_data = SignalSourceData(
            id=uuid.uuid4(),
            account_id=sample_account_id,
            signal_type="camera",
            name="Test Camera",
            status="active",
            config={},
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(Exception):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a signal source by ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: SignalSourceRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_id)

        assert isinstance(data, SignalSourceData)
        assert data.id == sample_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: SignalSourceRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: SignalSourceRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("delete failed")

        with pytest.raises(Exception):
            await repo.delete(sample_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """SignalSourceData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = SignalSourceData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            signal_type="camera",
            name="Test Camera",
            status="active",
            config={},
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]
