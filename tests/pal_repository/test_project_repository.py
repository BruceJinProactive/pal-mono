"""Tests for pal_repository.ProjectRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only ProjectData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.tables.projects import Project
from pal_repository.data_classes.project import ProjectData
from pal_repository.project import ProjectRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> ProjectRepository:
    return ProjectRepository(mock_session)


@pytest.fixture
def sample_project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_account_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_agent_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_project_id: uuid.UUID,
    sample_account_id: uuid.UUID,
    sample_agent_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=Project)
    row.id = sample_project_id
    row.name = "test-project"
    row.account_id = sample_account_id
    row.agent_id = sample_agent_id
    row.display_name = "Test Project"
    row.raw_config = {"key": "value"}
    row.channel_identifiers = ["voice:+15551234567"]
    row.store_hours = "Mon-Fri 9-5"
    row.address = "123 Main St"
    row.product_info = None
    row.service_instruction = None
    row.order_integration_id = None
    row.timezone = "America/Los_Angeles"
    row.transfer_message = None
    row.transfer_phone_number = None
    row.show_agent_caller_id = True
    row.reservation_link = None
    row.ordering_link = None
    row.call_forwarding_setup_completed = True
    row.stripe_customer_id = None
    row.stripe_coupon_id = None
    row.current_subscription_id = None
    row.google_place_id = None
    row.business_hours = None
    row.business_hours_last_updated = None
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    """Lookup by primary key — used when loading a specific project."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_project_id)

        assert isinstance(data, ProjectData)
        assert data.id == sample_project_id
        assert data.name == "test-project"
        assert data.display_name == "Test Project"
        assert data.raw_config == {"key": "value"}
        assert data.channel_identifiers == ["voice:+15551234567"]

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByName
# ---------------------------------------------------------------------------


class TestGetByName:
    """Lookup by unique project name."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_name("test-project")

        assert isinstance(data, ProjectData)
        assert data.name == "test-project"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_name("nonexistent")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("timeout")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_name("any")


# ---------------------------------------------------------------------------
# TestListByAccountId
# ---------------------------------------------------------------------------


class TestListByAccountId:
    """List all projects for an account — used by account management."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account_id(sample_account_id)

        assert len(results) == 1
        assert isinstance(results[0], ProjectData)
        assert results[0].account_id == sample_account_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_account_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("timeout")

        with pytest.raises(SQLAlchemyError):
            await repo.list_by_account_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByIds
# ---------------------------------------------------------------------------


class TestListByIds:
    """Batch fetch projects by IDs."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_ids([sample_project_id])

        assert len(results) == 1
        assert isinstance(results[0], ProjectData)
        assert results[0].id == sample_project_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_input(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        results = await repo.list_by_ids([])
        assert results == []
        mock_session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.list_by_ids([uuid.uuid4()])


# ---------------------------------------------------------------------------
# TestGetByChannelIdentifier
# ---------------------------------------------------------------------------


class TestGetByChannelIdentifier:
    """Lookup by channel identifier — used for inbound routing."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_channel_identifier("voice:+15551234567")

        assert isinstance(data, ProjectData)
        assert data.channel_identifiers == ["voice:+15551234567"]

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_channel_identifier("voice:+10000000000")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_channel_identifier("voice:+15551234567")


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new project."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
        sample_agent_id: uuid.UUID,
    ) -> None:
        input_data = ProjectData(
            id=uuid.uuid4(),
            name="new-project",
            account_id=sample_account_id,
            agent_id=sample_agent_id,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            display_name="New Project",
            raw_config={"key": "value"},
            channel_identifiers=["voice:+15559999999"],
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
        sample_agent_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        input_data = ProjectData(
            id=uuid.uuid4(),
            name="fail-project",
            account_id=sample_account_id,
            agent_id=sample_agent_id,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(SQLAlchemyError):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------


class TestUpdate:
    """Updating project data fields."""

    @pytest.mark.asyncio
    async def test_update_commits(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_account_id: uuid.UUID,
        sample_agent_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        update_data = ProjectData(
            id=uuid.uuid4(),
            name="updated-project",
            account_id=sample_account_id,
            agent_id=sample_agent_id,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            display_name="Updated Project",
            address="456 Oak Ave",
        )

        await repo.update(project_id=sample_project_id, record=update_data)

        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_skips_when_not_found(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
        sample_agent_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        update_data = ProjectData(
            id=uuid.uuid4(),
            name="x",
            account_id=sample_account_id,
            agent_id=sample_agent_id,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.update(project_id=uuid.uuid4(), record=update_data)
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_only_sets_non_none_fields(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_account_id: uuid.UUID,
        sample_agent_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        # Only update display_name and address; leave optional fields as None
        # so they should NOT overwrite existing values.
        update_data = ProjectData(
            id=uuid.uuid4(),
            name="test-project",
            account_id=sample_account_id,
            agent_id=sample_agent_id,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            display_name="Updated Display",
            address="789 Elm St",
        )

        await repo.update(
            project_id=sample_project_id,
            record=update_data,
        )

        # display_name and address were set
        assert sample_orm_row.display_name == "Updated Display"
        assert sample_orm_row.address == "789 Elm St"
        # timezone was NOT overwritten (still the original value from fixture)
        assert sample_orm_row.timezone == "America/Los_Angeles"
        # boolean fields were NOT reset (None in record means "don't change")
        assert sample_orm_row.show_agent_caller_id is True
        assert sample_orm_row.call_forwarding_setup_completed is True

    @pytest.mark.asyncio
    async def test_update_raises_on_db_error(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_account_id: uuid.UUID,
        sample_agent_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("update failed")

        update_data = ProjectData(
            id=uuid.uuid4(),
            name="fail",
            account_id=sample_account_id,
            agent_id=sample_agent_id,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(SQLAlchemyError):
            await repo.update(
                project_id=sample_project_id,
                record=update_data,
            )
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a project."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_project_id)

        assert isinstance(data, ProjectData)
        assert data.id == sample_project_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: ProjectRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: ProjectRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("delete failed")

        with pytest.raises(SQLAlchemyError):
            await repo.delete(sample_project_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """ProjectData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = ProjectData(
            id=uuid.uuid4(),
            name="immutable-project",
            account_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]

    def test_raw_config_defaults_to_empty_dict(self) -> None:
        data = ProjectData(
            id=uuid.uuid4(),
            name="default-config",
            account_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        assert data.raw_config == {}

    def test_channel_identifiers_defaults_to_empty_list(self) -> None:
        data = ProjectData(
            id=uuid.uuid4(),
            name="default-channels",
            account_id=uuid.uuid4(),
            agent_id=uuid.uuid4(),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        assert data.channel_identifiers == []
