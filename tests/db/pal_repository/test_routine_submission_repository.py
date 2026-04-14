"""Tests for db.pal_repository.RoutineSubmissionRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only RoutineSubmissionData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.routine_submission import RoutineSubmissionData
from db.pal_repository.routine_submission import RoutineSubmissionRepository
from db.tables.routine_submissions import RoutineSubmission

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> RoutineSubmissionRepository:
    return RoutineSubmissionRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_execution_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_execution_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=RoutineSubmission)
    row.id = sample_id
    row.execution_id = sample_execution_id
    status_mock = MagicMock()
    status_mock.value = "submitted"
    row.status = status_mock
    row.submitted_by = uuid.uuid4()
    row.submitted_at = datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc)
    row.reviewed_by = None
    row.reviewed_at = None
    row.review_notes = None
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
        repo: RoutineSubmissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, RoutineSubmissionData)
        assert data.id == sample_id
        assert data.status == "submitted"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: RoutineSubmissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineSubmissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByExecutionId
# ---------------------------------------------------------------------------


class TestGetByExecutionId:
    """Lookup by execution ID (1:1 relationship)."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: RoutineSubmissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_execution_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_execution_id(sample_execution_id)

        assert isinstance(data, RoutineSubmissionData)
        assert data.execution_id == sample_execution_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: RoutineSubmissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_execution_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineSubmissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("timeout")

        with pytest.raises(RuntimeError, match="timeout"):
            await repo.get_by_execution_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByStatus
# ---------------------------------------------------------------------------


class TestListByStatus:
    """List submissions filtered by status."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: RoutineSubmissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_status("submitted")

        assert len(results) == 1
        assert isinstance(results[0], RoutineSubmissionData)
        assert results[0].status == "submitted"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: RoutineSubmissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_status("draft")
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RoutineSubmissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("error")

        with pytest.raises(RuntimeError, match="error"):
            await repo.list_by_status("submitted")


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new routine submission."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: RoutineSubmissionRepository,
        mock_session: AsyncMock,
        sample_execution_id: uuid.UUID,
    ) -> None:
        input_data = RoutineSubmissionData(
            id=uuid.uuid4(),
            execution_id=sample_execution_id,
            status="submitted",
            submitted_by=uuid.uuid4(),
            submitted_at=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: RoutineSubmissionRepository,
        mock_session: AsyncMock,
        sample_execution_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = RuntimeError("insert failed")

        input_data = RoutineSubmissionData(
            id=uuid.uuid4(),
            execution_id=sample_execution_id,
            status="draft",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(RuntimeError, match="insert failed"):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a routine submission by ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: RoutineSubmissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_id)

        assert isinstance(data, RoutineSubmissionData)
        assert data.id == sample_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: RoutineSubmissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: RoutineSubmissionRepository,
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
    """RoutineSubmissionData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = RoutineSubmissionData(
            id=uuid.uuid4(),
            execution_id=uuid.uuid4(),
            status="draft",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.status = "changed"  # type: ignore[misc]
