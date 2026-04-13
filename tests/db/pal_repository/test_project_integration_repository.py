"""Tests for db.pal_repository.ProjectIntegrationRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only ProjectIntegrationData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.project_integration import ProjectIntegrationData
from db.pal_repository.project_integration import ProjectIntegrationRepository
from db.tables.integration import ProjectIntegration

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> ProjectIntegrationRepository:
    return ProjectIntegrationRepository(mock_session)


@pytest.fixture
def sample_pi_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_integration_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_pi_id: uuid.UUID,
    sample_project_id: uuid.UUID,
    sample_integration_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=ProjectIntegration)
    row.id = sample_pi_id
    row.project_id = sample_project_id
    row.integration_id = sample_integration_id
    row.store_identifier = "store-001"
    row.tool_name = "toast_v2"
    row.config = {"menu_data": {"items": []}}
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    """Lookup by primary key — used when loading a specific project integration."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_pi_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_pi_id)

        assert isinstance(data, ProjectIntegrationData)
        assert data.id == sample_pi_id
        assert data.store_identifier == "store-001"
        assert data.tool_name == "toast_v2"
        assert data.config == {"menu_data": {"items": []}}

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: ProjectIntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectIntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestListByProjectId
# ---------------------------------------------------------------------------


class TestListByProjectId:
    """List all integrations for a project — used by integration service."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: ProjectIntegrationRepository,
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
        assert isinstance(results[0], ProjectIntegrationData)
        assert results[0].project_id == sample_project_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: ProjectIntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_project_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectIntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("timeout")

        with pytest.raises(SQLAlchemyError):
            await repo.list_by_project_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByIntegrationId
# ---------------------------------------------------------------------------


class TestListByIntegrationId:
    """Reverse lookup — find all projects linked to an integration."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_integration_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_integration_id(sample_integration_id)

        assert len(results) == 1
        assert results[0].integration_id == sample_integration_id

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectIntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.list_by_integration_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByProjectAndIntegration
# ---------------------------------------------------------------------------


class TestGetByProjectAndIntegration:
    """Exact lookup by both project and integration IDs."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_integration_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_project_and_integration(
            sample_project_id, sample_integration_id
        )

        assert isinstance(data, ProjectIntegrationData)
        assert data.project_id == sample_project_id
        assert data.integration_id == sample_integration_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: ProjectIntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_project_and_integration(uuid.uuid4(), uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectIntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_project_and_integration(uuid.uuid4(), uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new project-integration link."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
        sample_integration_id: uuid.UUID,
    ) -> None:
        input_data = ProjectIntegrationData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            integration_id=sample_integration_id,
            store_identifier="store-new",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tool_name="adora_v3",
            config={"key": "value"},
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
        sample_integration_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        input_data = ProjectIntegrationData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            integration_id=sample_integration_id,
            store_identifier="store-fail",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(SQLAlchemyError):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------


class TestUpdate:
    """Updating project integration config (e.g. menu data refresh)."""

    @pytest.mark.asyncio
    async def test_update_commits(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_pi_id: uuid.UUID,
        sample_project_id: uuid.UUID,
        sample_integration_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        update_data = ProjectIntegrationData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            integration_id=sample_integration_id,
            store_identifier="store-updated",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            config={"new": "data"},
        )

        await repo.update(
            project_integration_id=sample_pi_id,
            record=update_data,
        )

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_skips_when_not_found(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
        sample_integration_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        update_data = ProjectIntegrationData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            integration_id=sample_integration_id,
            store_identifier="x",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.update(project_integration_id=uuid.uuid4(), record=update_data)
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_only_sets_non_none_fields(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_pi_id: uuid.UUID,
        sample_project_id: uuid.UUID,
        sample_integration_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        # Only update config; store_identifier and tool_name come from input but
        # tool_name is None so it should not overwrite the existing value.
        update_data = ProjectIntegrationData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            integration_id=sample_integration_id,
            store_identifier="store-001",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            config={"updated": True},
        )

        await repo.update(
            project_integration_id=sample_pi_id,
            record=update_data,
        )

        # store_identifier was set (same value)
        assert sample_orm_row.store_identifier == "store-001"
        # tool_name was NOT overwritten (still the original value from fixture)
        assert sample_orm_row.tool_name == "toast_v2"

    @pytest.mark.asyncio
    async def test_update_raises_on_db_error(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_pi_id: uuid.UUID,
        sample_project_id: uuid.UUID,
        sample_integration_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("update failed")

        update_data = ProjectIntegrationData(
            id=uuid.uuid4(),
            project_id=sample_project_id,
            integration_id=sample_integration_id,
            store_identifier="fail",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(SQLAlchemyError):
            await repo.update(
                project_integration_id=sample_pi_id,
                record=update_data,
            )
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a project-integration link."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_pi_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_pi_id)

        assert isinstance(data, ProjectIntegrationData)
        assert data.id == sample_pi_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: ProjectIntegrationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: ProjectIntegrationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_pi_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("delete failed")

        with pytest.raises(SQLAlchemyError):
            await repo.delete(sample_pi_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """ProjectIntegrationData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = ProjectIntegrationData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            integration_id=uuid.uuid4(),
            store_identifier="store-x",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.store_identifier = "changed"  # type: ignore[misc]

    def test_config_defaults_to_empty_dict(self) -> None:
        data = ProjectIntegrationData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            integration_id=uuid.uuid4(),
            store_identifier="store-y",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        assert data.config == {}
