"""Tests for db.pal_repository.RoutineScheduleRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only RoutineScheduleData instances are returned.
"""

import uuid
from datetime import datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.routine_schedule import RoutineScheduleData
from db.pal_repository.routine_schedule import RoutineScheduleRepository
from db.tables.routine_schedules import RoutineSchedule

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> RoutineScheduleRepository:
    return RoutineScheduleRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_routine_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_routine_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=RoutineSchedule)
    row.id = sample_id
    row.routine_id = sample_routine_id
    freq_mock = MagicMock()
    freq_mock.value = "daily"
    row.frequency = freq_mock
    row.start_time = time(9, 0)
    row.end_time = time(17, 0)
    row.timezone = "America/Los_Angeles"
    row.days_of_week = [1, 2, 3, 4, 5]
    row.day_of_month = None
    row.interval_hours = None
    row.effective_from = None
    row.effective_until = None
    row.is_active = True
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
        repo: RoutineScheduleRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, RoutineScheduleData)
        assert data.id == sample_id
        assert data.frequency == "daily"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: RoutineScheduleRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineScheduleRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByRoutineId
# ---------------------------------------------------------------------------


class TestListByRoutineId:
    """List all schedules for a routine."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: RoutineScheduleRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_routine_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_routine_id(sample_routine_id)

        assert len(results) == 1
        assert isinstance(results[0], RoutineScheduleData)
        assert results[0].routine_id == sample_routine_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: RoutineScheduleRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_routine_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineScheduleRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("timeout")

        with pytest.raises(RuntimeError, match="timeout"):
            await repo.list_by_routine_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListActiveByRoutineId
# ---------------------------------------------------------------------------


class TestListActiveByRoutineId:
    """List only active schedules for a routine."""

    @pytest.mark.asyncio
    async def test_returns_active_schedules(
        self,
        repo: RoutineScheduleRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_routine_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_active_by_routine_id(sample_routine_id)

        assert len(results) == 1
        assert results[0].is_active is True

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_active(
        self, repo: RoutineScheduleRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_active_by_routine_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineScheduleRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("error")

        with pytest.raises(RuntimeError, match="error"):
            await repo.list_active_by_routine_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new routine schedule."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: RoutineScheduleRepository,
        mock_session: AsyncMock,
        sample_routine_id: uuid.UUID,
    ) -> None:
        input_data = RoutineScheduleData(
            id=uuid.uuid4(),
            routine_id=sample_routine_id,
            frequency="daily",
            start_time=time(9, 0),
            end_time=time(17, 0),
            timezone="America/Los_Angeles",
            is_active=True,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            days_of_week=(1, 2, 3, 4, 5),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: RoutineScheduleRepository,
        mock_session: AsyncMock,
        sample_routine_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = RuntimeError("insert failed")

        input_data = RoutineScheduleData(
            id=uuid.uuid4(),
            routine_id=sample_routine_id,
            frequency="daily",
            start_time=time(9, 0),
            end_time=time(17, 0),
            timezone="America/Los_Angeles",
            is_active=True,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(RuntimeError, match="insert failed"):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a routine schedule by ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: RoutineScheduleRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_id)

        assert isinstance(data, RoutineScheduleData)
        assert data.id == sample_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: RoutineScheduleRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: RoutineScheduleRepository,
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
    """RoutineScheduleData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = RoutineScheduleData(
            id=uuid.uuid4(),
            routine_id=uuid.uuid4(),
            frequency="daily",
            start_time=time(9, 0),
            end_time=time(17, 0),
            timezone="America/Los_Angeles",
            is_active=True,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.frequency = "changed"  # type: ignore[misc]
