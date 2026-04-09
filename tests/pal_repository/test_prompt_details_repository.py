"""Tests for pal_repository.PromptDetailsRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only PromptDetailsData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.tables.prompts import PromptDetails
from pal_repository.data_classes.prompt_details import PromptDetailsData
from pal_repository.prompt_details import PromptDetailsRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> PromptDetailsRepository:
    return PromptDetailsRepository(mock_session)


@pytest.fixture
def sample_prompt_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_details_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_details(
    sample_details_id: uuid.UUID,
    sample_prompt_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=PromptDetails)
    row.id = sample_details_id
    row.prompt_id = sample_prompt_id
    row.version_number = 3
    row.content = "Hello, welcome to our restaurant."
    row.created_by = "user-abc"
    row.created_at = datetime(2025, 6, 5, tzinfo=timezone.utc)
    row.updated_at = None
    row.change_summary = "Updated greeting"
    return row


# ---------------------------------------------------------------------------
# TestGetLatest
# ---------------------------------------------------------------------------


class TestGetLatest:
    """Retrieve latest prompt version."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: PromptDetailsRepository,
        mock_session: AsyncMock,
        sample_orm_details: MagicMock,
        sample_prompt_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_details
        mock_session.execute.return_value = mock_result

        data = await repo.get_latest(sample_prompt_id)

        assert isinstance(data, PromptDetailsData)
        assert data.version_number == 3
        assert data.content == "Hello, welcome to our restaurant."
        assert data.change_summary == "Updated greeting"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_versions(
        self, repo: PromptDetailsRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_latest(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_no_rollback_on_read_error(
        self, repo: PromptDetailsRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        with pytest.raises(Exception, match="timeout"):
            await repo.get_latest(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestListByPromptId
# ---------------------------------------------------------------------------


class TestListByPromptId:
    """List all versions for a prompt."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: PromptDetailsRepository,
        mock_session: AsyncMock,
        sample_orm_details: MagicMock,
        sample_prompt_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_details]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_prompt_id(sample_prompt_id)

        assert len(results) == 1
        assert isinstance(results[0], PromptDetailsData)
        assert results[0].prompt_id == sample_prompt_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_versions(
        self, repo: PromptDetailsRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_prompt_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_no_rollback_on_read_error(
        self, repo: PromptDetailsRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        with pytest.raises(Exception, match="timeout"):
            await repo.list_by_prompt_id(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new prompt version."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: PromptDetailsRepository,
        mock_session: AsyncMock,
        sample_prompt_id: uuid.UUID,
    ) -> None:
        input_data = PromptDetailsData(
            id=uuid.uuid4(),
            prompt_id=sample_prompt_id,
            version_number=1,
            content="Welcome!",
            created_by="user-xyz",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
            change_summary="Initial version",
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        added_row = mock_session.add.call_args.args[0]
        assert added_row.id == input_data.id

    @pytest.mark.asyncio
    async def test_create_rolls_back_on_error(
        self,
        repo: PromptDetailsRepository,
        mock_session: AsyncMock,
        sample_prompt_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        input_data = PromptDetailsData(
            id=uuid.uuid4(),
            prompt_id=sample_prompt_id,
            version_number=1,
            content="Fail",
            created_by="user-xyz",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
        )

        with pytest.raises(Exception, match="insert failed"):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """PromptDetailsData is a frozen dataclass — mutations are disallowed."""

    def test_prompt_details_data_is_immutable(self) -> None:
        data = PromptDetailsData(
            id=uuid.uuid4(),
            prompt_id=uuid.uuid4(),
            version_number=1,
            content="test",
            created_by="user",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
        )
        with pytest.raises(AttributeError):
            data.content = "changed"  # type: ignore[misc]

    def test_change_summary_defaults_to_none(self) -> None:
        data = PromptDetailsData(
            id=uuid.uuid4(),
            prompt_id=uuid.uuid4(),
            version_number=1,
            content="test",
            created_by="user",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
        )
        assert data.change_summary is None
