"""Tests for pal_repository.RoutineRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.tables.routines import Routine
from db.tables.types import RoutineCategory
from pal_repository.data_classes.routine import RoutineData, RoutineUpdateData
from pal_repository.routine import RoutineRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> RoutineRepository:
    return RoutineRepository(mock_session)


@pytest.fixture
def sample_routine_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_routine_id: uuid.UUID,
    sample_project_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=Routine)
    row.id = sample_routine_id
    row.project_id = sample_project_id
    row.name = "Opening Checklist"
    row.description = "Daily opening tasks"
    row.category = RoutineCategory.opening
    row.is_active = True
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
        repo: RoutineRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_routine_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_routine_id)

        assert isinstance(data, RoutineData)
        assert data.id == sample_routine_id
        assert data.name == "Opening Checklist"
        assert data.category == RoutineCategory.opening

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: RoutineRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByProjectId
# ---------------------------------------------------------------------------


class TestListByProjectId:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: RoutineRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_project_id(sample_project_id)

        assert len(results) == 1
        assert results[0].project_id == sample_project_id

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: RoutineRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        assert await repo.list_by_project_id(uuid.uuid4()) == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")
        with pytest.raises(SQLAlchemyError):
            await repo.list_by_project_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: RoutineRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        input_data = RoutineData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            name="Closing Checklist",
            category=RoutineCategory.closing,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: RoutineRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        input_data = RoutineData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            name="Fail",
            category=RoutineCategory.custom,
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
        repo: RoutineRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_routine_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        update_data = RoutineUpdateData(
            name="Updated Checklist",
            category=RoutineCategory.closing,
            is_active=False,
        )

        await repo.update(sample_routine_id, update_data)

        mock_session.commit.assert_awaited_once()
        assert sample_orm_row.name == "Updated Checklist"
        assert sample_orm_row.is_active is False

    @pytest.mark.asyncio
    async def test_update_skips_when_not_found(
        self,
        repo: RoutineRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        update_data = RoutineUpdateData(name="x")

        await repo.update(uuid.uuid4(), update_data)
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_does_not_overwrite_none_fields(
        self,
        repo: RoutineRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_routine_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        # Only update name; leave description as None so it's not overwritten
        update_data = RoutineUpdateData(name="New Name")

        await repo.update(sample_routine_id, update_data)

        assert sample_orm_row.name == "New Name"
        # description was NOT overwritten (still original fixture value)
        assert sample_orm_row.description == "Daily opening tasks"
        # is_active was NOT overwritten (None in update_data)
        assert sample_orm_row.is_active is True

    @pytest.mark.asyncio
    async def test_update_raises_on_db_error(
        self,
        repo: RoutineRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_routine_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("update failed")

        update_data = RoutineUpdateData(name="x")

        with pytest.raises(SQLAlchemyError):
            await repo.update(sample_routine_id, update_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: RoutineRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_routine_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_routine_id)

        assert isinstance(data, RoutineData)
        assert data.id == sample_routine_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: RoutineRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.delete(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: RoutineRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_routine_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("delete failed")

        with pytest.raises(SQLAlchemyError):
            await repo.delete(sample_routine_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_data_is_immutable(self) -> None:
        data = RoutineData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            name="Immutable",
            category=RoutineCategory.custom,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]
