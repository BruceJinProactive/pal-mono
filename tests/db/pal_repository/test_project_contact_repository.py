"""Tests for db.pal_repository.ProjectContactRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only ProjectContactData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.project_contact import ProjectContactData
from db.pal_repository.project_contact import ProjectContactRepository
from db.tables.project_contacts import ProjectContact

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> ProjectContactRepository:
    return ProjectContactRepository(mock_session)


@pytest.fixture
def sample_pc_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_contact_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_pc_id: uuid.UUID,
    sample_project_id: uuid.UUID,
    sample_contact_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=ProjectContact)
    row.id = sample_pc_id
    row.project_id = sample_project_id
    row.contact_id = sample_contact_id
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    """Lookup by primary key — used when loading a specific project contact."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_pc_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_pc_id)

        assert isinstance(data, ProjectContactData)
        assert data.id == sample_pc_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByProjectId
# ---------------------------------------------------------------------------


class TestGetByProjectId:
    """List all contacts for a project."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_project_id(sample_project_id)

        assert len(results) == 1
        assert isinstance(results[0], ProjectContactData)
        assert results[0].project_id == sample_project_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_project_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("timeout")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_project_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByContactId
# ---------------------------------------------------------------------------


class TestGetByContactId:
    """Reverse lookup — find all projects linked to a contact."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_contact_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_contact_id(sample_contact_id)

        assert len(results) == 1
        assert results[0].contact_id == sample_contact_id

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_contact_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByProjectAndContact
# ---------------------------------------------------------------------------


class TestGetByProjectAndContact:
    """Exact lookup by both project and contact IDs."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_contact_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_project_and_contact(
            sample_project_id, sample_contact_id
        )

        assert isinstance(data, ProjectContactData)
        assert data.project_id == sample_project_id
        assert data.contact_id == sample_contact_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_project_and_contact(uuid.uuid4(), uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_project_and_contact(uuid.uuid4(), uuid.uuid4())


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new project-contact link."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
        sample_contact_id: uuid.UUID,
    ) -> None:
        input_data = ProjectContactData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            contact_id=sample_contact_id,
        )

        result = await repo.create(input_data)

        assert result is None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
        sample_contact_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        input_data = ProjectContactData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            contact_id=sample_contact_id,
        )

        with pytest.raises(SQLAlchemyError):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a project-contact link."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_pc_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_pc_id)

        assert isinstance(data, ProjectContactData)
        assert data.id == sample_pc_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_pc_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("delete failed")

        with pytest.raises(SQLAlchemyError):
            await repo.delete(sample_pc_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TestListContactIdsByProject
# ---------------------------------------------------------------------------


class TestListContactIdsByProject:
    """List only the contact UUIDs for a project."""

    @pytest.mark.asyncio
    async def test_returns_list_of_uuids(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_contact_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_contact_id]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.list_contact_ids_by_project(uuid.uuid4())

        assert result == [sample_contact_id]

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.list_contact_ids_by_project(uuid.uuid4())
        assert result == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("error")

        with pytest.raises(RuntimeError, match="error"):
            await repo.list_contact_ids_by_project(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestDeleteByProjectAndContact
# ---------------------------------------------------------------------------


class TestDeleteByProjectAndContact:
    """Delete by composite project + contact key."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_contact_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete_by_project_and_contact(
            sample_project_id, sample_contact_id
        )

        assert isinstance(data, ProjectContactData)
        assert data.project_id == sample_project_id
        assert data.contact_id == sample_contact_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: ProjectContactRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete_by_project_and_contact(uuid.uuid4(), uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: ProjectContactRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_contact_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = RuntimeError("delete failed")

        with pytest.raises(RuntimeError, match="delete failed"):
            await repo.delete_by_project_and_contact(
                sample_project_id, sample_contact_id
            )
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """ProjectContactData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = ProjectContactData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            contact_id=uuid.uuid4(),
        )
        with pytest.raises(AttributeError):
            data.contact_id = uuid.uuid4()  # type: ignore[misc]
