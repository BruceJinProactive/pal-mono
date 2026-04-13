"""Tests for db.pal_repository.RolePermissionRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only RolePermissionData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.role_permission import RolePermissionData
from db.pal_repository.role_permission import RolePermissionRepository
from db.tables.role_permission import RolePermission

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> RolePermissionRepository:
    return RolePermissionRepository(mock_session)


@pytest.fixture
def sample_rp_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_permission_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_rp_id: uuid.UUID,
    sample_permission_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=RolePermission)
    row.id = sample_rp_id
    row.role = "owner"
    row.permission_id = sample_permission_id
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
        repo: RolePermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_rp_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_rp_id)

        assert isinstance(data, RolePermissionData)
        assert data.id == sample_rp_id
        assert data.role == "owner"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: RolePermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RolePermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByRole
# ---------------------------------------------------------------------------


class TestListByRole:
    """List all permission mappings for a role."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: RolePermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_role("owner")

        assert len(results) == 1
        assert isinstance(results[0], RolePermissionData)
        assert results[0].role == "owner"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: RolePermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_role("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RolePermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("timeout")

        with pytest.raises(SQLAlchemyError):
            await repo.list_by_role("owner")


# ---------------------------------------------------------------------------
# TestListByPermissionId
# ---------------------------------------------------------------------------


class TestListByPermissionId:
    """Reverse lookup — find all roles linked to a permission."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: RolePermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_permission_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_permission_id(sample_permission_id)

        assert len(results) == 1
        assert results[0].permission_id == sample_permission_id

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RolePermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.list_by_permission_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByRoleAndPermission
# ---------------------------------------------------------------------------


class TestGetByRoleAndPermission:
    """Exact lookup by both role and permission ID."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: RolePermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_permission_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_role_and_permission("owner", sample_permission_id)

        assert isinstance(data, RolePermissionData)
        assert data.role == "owner"
        assert data.permission_id == sample_permission_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: RolePermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_role_and_permission("viewer", uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: RolePermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_role_and_permission("owner", uuid.uuid4())


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new role-permission mapping."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: RolePermissionRepository,
        mock_session: AsyncMock,
        sample_permission_id: uuid.UUID,
    ) -> None:
        input_data = RolePermissionData(
            id=uuid.uuid4(),
            role="manager",
            permission_id=sample_permission_id,
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: RolePermissionRepository,
        mock_session: AsyncMock,
        sample_permission_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        input_data = RolePermissionData(
            id=uuid.uuid4(),
            role="manager",
            permission_id=sample_permission_id,
        )

        with pytest.raises(SQLAlchemyError):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a role-permission mapping by ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: RolePermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_rp_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_rp_id)

        assert isinstance(data, RolePermissionData)
        assert data.id == sample_rp_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: RolePermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: RolePermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_rp_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("delete failed")

        with pytest.raises(SQLAlchemyError):
            await repo.delete(sample_rp_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDeleteByRoleAndPermission
# ---------------------------------------------------------------------------


class TestDeleteByRoleAndPermission:
    """Deleting a role-permission mapping by role and permission ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: RolePermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_permission_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete_by_role_and_permission("owner", sample_permission_id)

        assert isinstance(data, RolePermissionData)
        assert data.role == "owner"
        assert data.permission_id == sample_permission_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: RolePermissionRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete_by_role_and_permission("viewer", uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: RolePermissionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_permission_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("delete failed")

        with pytest.raises(SQLAlchemyError):
            await repo.delete_by_role_and_permission("owner", sample_permission_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """RolePermissionData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = RolePermissionData(
            id=uuid.uuid4(),
            role="owner",
            permission_id=uuid.uuid4(),
        )
        with pytest.raises(AttributeError):
            data.role = "changed"  # type: ignore[misc]
