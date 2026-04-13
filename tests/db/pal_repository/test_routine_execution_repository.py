"""Tests for db.pal_repository.RoutineExecutionRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.routine_execution import (
    RoutineExecutionData,
    RoutineExecutionUpdateData,
)
from db.pal_repository.routine_execution import RoutineExecutionRepository
from db.tables.routine_executions import RoutineExecution
from db.tables.types import ExecutionStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> RoutineExecutionRepository:
    return RoutineExecutionRepository(mock_session)


@pytest.fixture
def sample_execution_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_routine_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_schedule_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_execution_id: uuid.UUID,
    sample_routine_id: uuid.UUID,
    sample_schedule_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=RoutineExecution)
    row.id = sample_execution_id
    row.routine_id = sample_routine_id
    row.schedule_id = sample_schedule_id
    row.scheduled_start = datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc)
    row.scheduled_end = datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc)
    row.status = ExecutionStatus.pending
    row.assigned_user_id = None
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: RoutineExecutionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_execution_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_execution_id)

        assert isinstance(data, RoutineExecutionData)
        assert data.id == sample_execution_id
        assert data.status == ExecutionStatus.pending

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: RoutineExecutionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineExecutionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByRoutineId
# ---------------------------------------------------------------------------


class TestListByRoutineId:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: RoutineExecutionRepository,
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
        assert results[0].routine_id == sample_routine_id

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: RoutineExecutionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        assert await repo.list_by_routine_id(uuid.uuid4()) == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineExecutionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")
        with pytest.raises(SQLAlchemyError):
            await repo.list_by_routine_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByScheduleId
# ---------------------------------------------------------------------------


class TestListByScheduleId:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: RoutineExecutionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_schedule_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_schedule_id(sample_schedule_id)

        assert len(results) == 1
        assert results[0].schedule_id == sample_schedule_id

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineExecutionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")
        with pytest.raises(SQLAlchemyError):
            await repo.list_by_schedule_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: RoutineExecutionRepository,
        mock_session: AsyncMock,
        sample_routine_id: uuid.UUID,
        sample_schedule_id: uuid.UUID,
    ) -> None:
        input_data = RoutineExecutionData(
            id=uuid.uuid4(),
            routine_id=sample_routine_id,
            schedule_id=sample_schedule_id,
            scheduled_start=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
            status=ExecutionStatus.pending,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: RoutineExecutionRepository,
        mock_session: AsyncMock,
        sample_routine_id: uuid.UUID,
        sample_schedule_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        input_data = RoutineExecutionData(
            id=uuid.uuid4(),
            routine_id=sample_routine_id,
            schedule_id=sample_schedule_id,
            scheduled_start=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
            status=ExecutionStatus.pending,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(SQLAlchemyError):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_commits(
        self,
        repo: RoutineExecutionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_execution_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        update_data = RoutineExecutionUpdateData(
            status=ExecutionStatus.completed,
        )

        await repo.update(sample_execution_id, update_data)

        mock_session.commit.assert_awaited_once()
        assert sample_orm_row.status == ExecutionStatus.completed

    @pytest.mark.asyncio
    async def test_update_skips_when_not_found(
        self,
        repo: RoutineExecutionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        update_data = RoutineExecutionUpdateData(status=ExecutionStatus.pending)

        await repo.update(uuid.uuid4(), update_data)
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_can_unassign_user(
        self,
        repo: RoutineExecutionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_execution_id: uuid.UUID,
    ) -> None:
        sample_orm_row.assigned_user_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        update_data = RoutineExecutionUpdateData(assigned_user_id=None)

        await repo.update(sample_execution_id, update_data)

        assert sample_orm_row.assigned_user_id is None
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_raises_on_db_error(
        self,
        repo: RoutineExecutionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_execution_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("update failed")

        update_data = RoutineExecutionUpdateData(status=ExecutionStatus.pending)

        with pytest.raises(SQLAlchemyError):
            await repo.update(sample_execution_id, update_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: RoutineExecutionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_execution_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_execution_id)

        assert isinstance(data, RoutineExecutionData)
        assert data.id == sample_execution_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: RoutineExecutionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.delete(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: RoutineExecutionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_execution_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("delete failed")

        with pytest.raises(SQLAlchemyError):
            await repo.delete(sample_execution_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_data_is_immutable(self) -> None:
        data = RoutineExecutionData(
            id=uuid.uuid4(),
            routine_id=uuid.uuid4(),
            schedule_id=uuid.uuid4(),
            scheduled_start=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            scheduled_end=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
            status=ExecutionStatus.pending,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.status = ExecutionStatus.completed  # type: ignore[misc]
