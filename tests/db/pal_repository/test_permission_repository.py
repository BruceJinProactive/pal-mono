"""Tests for db.pal_repository.PermissionRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only PermissionData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.permission import PermissionData
from db.pal_repository.permission import PermissionRepository
from db.tables.permission import Permission

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> PermissionRepository:
    return PermissionRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=Permission)
    row.id = sample_id
    row.name = "project.create"
    row.resource_type = "project"
    row.action = "create"
    row.display_name = "Create Project"
    row.description = "Allows creating a new project"
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    """Lookup by primary key."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: PermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, PermissionData)
        assert data.id == sample_id
        assert data.name == "project.create"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: PermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: PermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        with pytest.raises(Exception):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByName
# ---------------------------------------------------------------------------


class TestGetByName:
    """Lookup by unique name."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: PermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_name("project.create")

        assert isinstance(data, PermissionData)
        assert data.name == "project.create"
        assert data.resource_type == "project"
        assert data.action == "create"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: PermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_name("nonexistent.perm")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: PermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        with pytest.raises(Exception):
            await repo.get_by_name("project.create")


# ---------------------------------------------------------------------------
# TestListByResourceType
# ---------------------------------------------------------------------------


class TestListByResourceType:
    """List permissions by resource type."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: PermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_resource_type("project")

        assert len(results) == 1
        assert isinstance(results[0], PermissionData)
        assert results[0].resource_type == "project"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: PermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_resource_type("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: PermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        with pytest.raises(Exception):
            await repo.list_by_resource_type("project")


# ---------------------------------------------------------------------------
# TestListAll
# ---------------------------------------------------------------------------


class TestListAll:
    """List all permissions."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: PermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_all()

        assert len(results) == 1
        assert isinstance(results[0], PermissionData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: PermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_all()
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: PermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        with pytest.raises(Exception):
            await repo.list_all()


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new permission."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: PermissionRepository,
        mock_session: AsyncMock,
    ) -> None:
        input_data = PermissionData(
            id=uuid.uuid4(),
            name="project.create",
            resource_type="project",
            action="create",
            display_name="Create Project",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: PermissionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        input_data = PermissionData(
            id=uuid.uuid4(),
            name="project.create",
            resource_type="project",
            action="create",
            display_name="Create Project",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(Exception):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a permission by ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: PermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_id)

        assert isinstance(data, PermissionData)
        assert data.id == sample_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: PermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: PermissionRepository,
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
# TestDeleteByName
# ---------------------------------------------------------------------------


class TestDeleteByName:
    """Deleting a permission by name."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: PermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete_by_name("project.create")

        assert isinstance(data, PermissionData)
        assert data.name == "project.create"
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: PermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete_by_name("nonexistent.perm")
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: PermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("delete failed")

        with pytest.raises(Exception):
            await repo.delete_by_name("project.create")
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """PermissionData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = PermissionData(
            id=uuid.uuid4(),
            name="project.create",
            resource_type="project",
            action="create",
            display_name="Create Project",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]
