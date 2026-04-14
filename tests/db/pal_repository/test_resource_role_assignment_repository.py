"""Tests for db.pal_repository.ResourceRoleAssignmentRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only ResourceRoleAssignmentData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.resource_role_assignment import (
    ResourceRoleAssignmentData,
)
from db.pal_repository.resource_role_assignment import ResourceRoleAssignmentRepository
from db.tables.resource_role_assignment import ResourceRoleAssignment

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> ResourceRoleAssignmentRepository:
    return ResourceRoleAssignmentRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_resource_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_user_id: uuid.UUID,
    sample_resource_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=ResourceRoleAssignment)
    row.id = sample_id
    row.user_id = sample_user_id
    row.resource_type = "project"
    row.resource_id = sample_resource_id
    row.role = "owner"
    row.assigned_by = None
    row.assigned_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.reason = None
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
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, ResourceRoleAssignmentData)
        assert data.id == sample_id
        assert data.role == "owner"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: ResourceRoleAssignmentRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ResourceRoleAssignmentRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        with pytest.raises(Exception):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByUser
# ---------------------------------------------------------------------------


class TestListByUser:
    """List all assignments for a user."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_user_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_user(sample_user_id)

        assert len(results) == 1
        assert isinstance(results[0], ResourceRoleAssignmentData)
        assert results[0].user_id == sample_user_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: ResourceRoleAssignmentRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_user(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_filters_by_resource_type(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_user_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_user(sample_user_id, resource_type="project")

        assert len(results) == 1
        assert results[0].resource_type == "project"

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ResourceRoleAssignmentRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        with pytest.raises(Exception):
            await repo.list_by_user(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByResource
# ---------------------------------------------------------------------------


class TestListByResource:
    """List all assignments for a specific resource."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_resource("project", sample_resource_id)

        assert len(results) == 1
        assert results[0].resource_id == sample_resource_id

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ResourceRoleAssignmentRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        with pytest.raises(Exception):
            await repo.list_by_resource("project", uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetRolesForResource
# ---------------------------------------------------------------------------


class TestGetRolesForResource:
    """Return role strings a user holds on a specific resource."""

    @pytest.mark.asyncio
    async def test_returns_role_list(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_user_id: uuid.UUID,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = ["owner", "billing_admin"]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        roles = await repo.get_roles_for_resource(
            sample_user_id, "project", sample_resource_id
        )

        assert roles == ["owner", "billing_admin"]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_roles(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        roles = await repo.get_roles_for_resource(uuid.uuid4(), "project", uuid.uuid4())
        assert roles == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ResourceRoleAssignmentRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        with pytest.raises(Exception):
            await repo.get_roles_for_resource(uuid.uuid4(), "project", uuid.uuid4())


# ---------------------------------------------------------------------------
# TestHasRole
# ---------------------------------------------------------------------------


class TestHasRole:
    """Check whether a user holds a specific role on a resource."""

    @pytest.mark.asyncio
    async def test_returns_true_when_role_exists(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_user_id: uuid.UUID,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid.uuid4()
        mock_session.execute.return_value = mock_result

        result = await repo.has_role(
            sample_user_id, "project", sample_resource_id, "owner"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_role_not_found(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.has_role(uuid.uuid4(), "project", uuid.uuid4(), "owner")
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ResourceRoleAssignmentRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("error")

        with pytest.raises(Exception):
            await repo.has_role(uuid.uuid4(), "project", uuid.uuid4(), "owner")


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new resource role assignment."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_user_id: uuid.UUID,
        sample_resource_id: uuid.UUID,
    ) -> None:
        input_data = ResourceRoleAssignmentData(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            resource_type="project",
            resource_id=sample_resource_id,
            role="owner",
            assigned_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_user_id: uuid.UUID,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        input_data = ResourceRoleAssignmentData(
            id=uuid.uuid4(),
            user_id=sample_user_id,
            resource_type="project",
            resource_id=sample_resource_id,
            role="owner",
            assigned_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(Exception):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting an assignment by ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_id)

        assert isinstance(data, ResourceRoleAssignmentData)
        assert data.id == sample_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: ResourceRoleAssignmentRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: ResourceRoleAssignmentRepository,
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
# TestDeleteByUserAndResource
# ---------------------------------------------------------------------------


class TestDeleteByUserAndResource:
    """Deleting a specific role assignment for a user on a resource."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_user_id: uuid.UUID,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete_by_user_and_resource(
            sample_user_id, "project", sample_resource_id, "owner"
        )

        assert isinstance(data, ResourceRoleAssignmentData)
        assert data.user_id == sample_user_id
        assert data.role == "owner"
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: ResourceRoleAssignmentRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete_by_user_and_resource(
            uuid.uuid4(), "project", uuid.uuid4(), "owner"
        )
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: ResourceRoleAssignmentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_user_id: uuid.UUID,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("delete failed")

        with pytest.raises(Exception):
            await repo.delete_by_user_and_resource(
                sample_user_id, "project", sample_resource_id, "owner"
            )
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """ResourceRoleAssignmentData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = ResourceRoleAssignmentData(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            resource_type="project",
            resource_id=uuid.uuid4(),
            role="owner",
            assigned_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.role = "changed"  # type: ignore[misc]
