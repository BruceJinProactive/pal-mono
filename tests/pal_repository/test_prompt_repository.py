"""Tests for pal_repository.PromptRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only PromptData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.tables.prompts import Prompt
from db.tables.types import Channel
from pal_repository.data_classes.prompt import PromptData
from pal_repository.prompt import PromptRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> PromptRepository:
    return PromptRepository(mock_session)


@pytest.fixture
def sample_prompt_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_resource_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_prompt(
    sample_prompt_id: uuid.UUID,
    sample_resource_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=Prompt)
    row.id = sample_prompt_id
    row.name = "greeting_prompt"
    row.resource_id = sample_resource_id
    row.resource_type = "agent"
    row.deleted = False
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 2, tzinfo=timezone.utc)
    row.default_prompt_id = None
    row.channel = [Channel.VOICE, Channel.SMS]
    return row


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    """Lookup by primary key — returns non-deleted prompts only."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: PromptRepository,
        mock_session: AsyncMock,
        sample_orm_prompt: MagicMock,
        sample_prompt_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_prompt
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_prompt_id)

        assert isinstance(data, PromptData)
        assert data.id == sample_prompt_id
        assert data.name == "greeting_prompt"
        assert data.resource_type == "agent"
        assert data.channel == ("voice", "sms")

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: PromptRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_no_rollback_on_read_error(
        self, repo: PromptRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("connection lost")

        with pytest.raises(Exception, match="connection lost"):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestListByResource
# ---------------------------------------------------------------------------


class TestListByResource:
    """List prompts filtered by resource type and ID."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: PromptRepository,
        mock_session: AsyncMock,
        sample_orm_prompt: MagicMock,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_prompt]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_resource("agent", sample_resource_id)

        assert len(results) == 1
        assert isinstance(results[0], PromptData)
        assert results[0].resource_id == sample_resource_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: PromptRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_resource("agent", uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_no_rollback_on_read_error(
        self, repo: PromptRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = Exception("timeout")

        with pytest.raises(Exception, match="timeout"):
            await repo.list_by_resource("agent", uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new prompt record."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: PromptRepository,
        mock_session: AsyncMock,
        sample_resource_id: uuid.UUID,
    ) -> None:
        input_data = PromptData(
            id=uuid.uuid4(),
            name="new_prompt",
            resource_id=sample_resource_id,
            resource_type="agent",
            deleted=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
            channel=("voice",),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        added_row = mock_session.add.call_args.args[0]
        assert added_row.id == input_data.id

    @pytest.mark.asyncio
    async def test_create_rolls_back_on_error(
        self,
        repo: PromptRepository,
        mock_session: AsyncMock,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = Exception("insert failed")

        input_data = PromptData(
            id=uuid.uuid4(),
            name="fail_prompt",
            resource_id=sample_resource_id,
            resource_type="agent",
            deleted=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
        )

        with pytest.raises(Exception, match="insert failed"):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------


class TestUpdate:
    """Updating prompt metadata."""

    @pytest.mark.asyncio
    async def test_update_commits(
        self,
        repo: PromptRepository,
        mock_session: AsyncMock,
        sample_orm_prompt: MagicMock,
        sample_prompt_id: uuid.UUID,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_prompt
        mock_session.execute.return_value = mock_result

        update_data = PromptData(
            id=sample_prompt_id,
            name="updated_prompt",
            resource_id=sample_resource_id,
            resource_type="agent",
            deleted=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
            channel=("voice", "email"),
        )

        await repo.update(sample_prompt_id, update_data)

        mock_session.commit.assert_awaited_once()
        assert sample_orm_prompt.name == "updated_prompt"

    @pytest.mark.asyncio
    async def test_update_skips_when_not_found(
        self,
        repo: PromptRepository,
        mock_session: AsyncMock,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        update_data = PromptData(
            id=uuid.uuid4(),
            name="x",
            resource_id=sample_resource_id,
            resource_type="agent",
            deleted=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
        )

        await repo.update(uuid.uuid4(), update_data)
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_rolls_back_on_error(
        self,
        repo: PromptRepository,
        mock_session: AsyncMock,
        sample_orm_prompt: MagicMock,
        sample_prompt_id: uuid.UUID,
        sample_resource_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_prompt
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("update failed")

        update_data = PromptData(
            id=sample_prompt_id,
            name="fail",
            resource_id=sample_resource_id,
            resource_type="agent",
            deleted=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
        )

        with pytest.raises(Exception, match="update failed"):
            await repo.update(sample_prompt_id, update_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Soft-deleting a prompt."""

    @pytest.mark.asyncio
    async def test_delete_sets_flag_and_commits(
        self,
        repo: PromptRepository,
        mock_session: AsyncMock,
        sample_orm_prompt: MagicMock,
        sample_prompt_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_prompt
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_prompt_id)

        assert isinstance(data, PromptData)
        assert data.id == sample_prompt_id
        assert sample_orm_prompt.deleted is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: PromptRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_rolls_back_on_error(
        self,
        repo: PromptRepository,
        mock_session: AsyncMock,
        sample_orm_prompt: MagicMock,
        sample_prompt_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_prompt
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = Exception("delete failed")

        with pytest.raises(Exception, match="delete failed"):
            await repo.delete(sample_prompt_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """PromptData is a frozen dataclass — mutations are disallowed."""

    def test_prompt_data_is_immutable(self) -> None:
        data = PromptData(
            id=uuid.uuid4(),
            name="test",
            resource_id=uuid.uuid4(),
            resource_type="agent",
            deleted=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]

    def test_channel_defaults_to_empty_tuple(self) -> None:
        data = PromptData(
            id=uuid.uuid4(),
            name="test",
            resource_id=uuid.uuid4(),
            resource_type="agent",
            deleted=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=None,
        )
        assert data.channel == ()
