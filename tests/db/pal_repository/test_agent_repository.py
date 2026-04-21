"""Tests for db.pal_repository.AgentRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.agent import AgentRepository
from db.pal_repository.data_classes.agent import AgentData


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> AgentRepository:
    return AgentRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = sample_id
    row.account_id = uuid.uuid4()
    row.name = "test"
    row.agent_type = MagicMock(value="inbound")
    row.speech_rate = MagicMock(value="normal")
    row.language = MagicMock(value="english")
    row.has_voice_clone = False
    row.background_noise = False
    row.memory_enabled = False
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.description = None
    row.communication_style = None
    row.interaction_guidelines = None
    row.voice_id = None
    row.cloned_voice_id = None
    row.greeting_message = None
    row.filler_words = {}
    row.raw_config = {}
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return row


class TestGetById:

    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: AgentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_id(uuid.uuid4())
        assert data is not None
        assert data.name == "test"

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: AgentRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: AgentRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_id(uuid.uuid4())


class TestListAgents:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: AgentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.list_agents(0, 10)
        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: AgentRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.list_agents()


class TestCreate:

    @pytest.mark.asyncio
    async def test_creates_and_returns_data(
        self,
        repo: AgentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(return_value=None)
        mock_session.refresh = AsyncMock(return_value=None)

        def capture_add(row: MagicMock) -> None:
            row.id = sample_orm_row.id
            row.account_id = sample_orm_row.account_id
            row.name = "test"
            row.agent_type = sample_orm_row.agent_type
            row.speech_rate = sample_orm_row.speech_rate
            row.language = sample_orm_row.language
            row.has_voice_clone = False
            row.background_noise = False
            row.memory_enabled = False
            row.created_at = sample_orm_row.created_at
            row.description = None
            row.communication_style = None
            row.interaction_guidelines = None
            row.voice_id = None
            row.cloned_voice_id = None
            row.greeting_message = None
            row.filler_words = {}
            row.raw_config = {}
            row.updated_at = None

        mock_session.add.side_effect = capture_add
        data = await repo.create(uuid.uuid4(), name="test")
        assert data is not None
        assert data.name == "test"
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ignores_non_mutable_fields(
        self,
        repo: AgentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(return_value=None)
        mock_session.refresh = AsyncMock(return_value=None)

        captured_rows: list[object] = []

        def capture_add(row: object) -> None:
            captured_rows.append(row)

        mock_session.add.side_effect = capture_add
        # id and account_id should NOT be set via kwargs (not in _MUTABLE_FIELDS)
        # We need to mock refresh to populate the row for _to_data
        mock_session.refresh.side_effect = (
            lambda row: setattr(row, "agent_type", sample_orm_row.agent_type)
            or setattr(row, "speech_rate", sample_orm_row.speech_rate)
            or setattr(row, "language", sample_orm_row.language)
            or setattr(row, "created_at", sample_orm_row.created_at)
        )

        data = await repo.create(uuid.uuid4(), id="should_be_ignored")
        # The Agent row should NOT have had `id` set by kwargs
        assert data is not None
        assert len(captured_rows) == 1
        created_row = captured_rows[0]
        assert getattr(created_row, "id") != "should_be_ignored"
        assert isinstance(getattr(created_row, "id"), uuid.UUID)

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: AgentRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.create(uuid.uuid4(), name="test")
        mock_session.rollback.assert_awaited_once()


class TestUpdate:

    @pytest.mark.asyncio
    async def test_update_found(
        self,
        repo: AgentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock(return_value=None)
        mock_session.refresh = AsyncMock(return_value=None)
        data = await repo.update(uuid.uuid4(), name="updated")
        assert data is not None

    @pytest.mark.asyncio
    async def test_update_not_found(
        self, repo: AgentRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.update(uuid.uuid4(), name="updated")
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self,
        repo: AgentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.update(uuid.uuid4(), name="updated")
        mock_session.rollback.assert_awaited_once()


class TestDelete:

    @pytest.mark.asyncio
    async def test_deletes_existing(
        self,
        repo: AgentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock(return_value=None)
        await repo.delete(uuid.uuid4())
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_is_noop(
        self, repo: AgentRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()
        await repo.delete(uuid.uuid4())
        mock_session.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self,
        repo: AgentRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.delete(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:

    def test_session_stored(
        self, repo: AgentRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self) -> None:
        """Verify AgentData cannot be mutated after creation."""
        sample_id = uuid.uuid4()
        data = AgentData(
            id=sample_id,
            account_id=uuid.uuid4(),
            name="test",
            agent_type="inbound",
            speech_rate="normal",
            language="english",
            has_voice_clone=False,
            background_noise=False,
            memory_enabled=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]

    def test_dict_fields_are_immutable(self) -> None:
        """Verify dict fields cannot be mutated in place."""
        data = AgentData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            name="test",
            agent_type="inbound",
            speech_rate="normal",
            language="english",
            has_voice_clone=False,
            background_noise=False,
            memory_enabled=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            filler_words={"um": "true"},
            raw_config={"key": "value", "nested": {"inner": "val"}},
        )
        with pytest.raises(TypeError):
            data.filler_words["new_key"] = "value"  # type: ignore[index]
        with pytest.raises(TypeError):
            data.raw_config["new_key"] = "value"  # type: ignore[index]
        # Nested dicts are also frozen
        with pytest.raises(TypeError):
            data.raw_config["nested"]["mutate"] = "fail"  # type: ignore[index]
