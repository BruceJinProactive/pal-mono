"""Tests for db.pal_repository.ConversationRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.conversation import ConversationRepository
from db.pal_repository.data_classes.conversation import ConversationData


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> ConversationRepository:
    return ConversationRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = sample_id
    row.user_id = uuid.uuid4()
    row.status = MagicMock(value="active")
    row.is_test = False
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.project_id = None
    row.channel = None
    row.purpose = None
    row.language = None
    row.ended_reason = None
    row.transfer_purpose = None
    row.customer_converted = None
    row.agent_fingerprint = None
    row.prompt_fingerprint = None
    row.vapi_control_url = None
    row.call_id = None
    row.updated_at = None
    return row


class TestGetById:

    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: ConversationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_id(sample_id)
        assert isinstance(data, ConversationData)
        assert data.id == sample_id
        assert data.status == "active"

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: ConversationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: ConversationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_id(uuid.uuid4())


class TestGetByCallId:

    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: ConversationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_call_id("call_123")
        assert data is not None

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: ConversationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.get_by_call_id("call_404")
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: ConversationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_call_id("call_123")


class TestGetByProject:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: ConversationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_by_project(uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_invalid_limit(self, repo: ConversationRepository) -> None:
        with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
            await repo.get_by_project(uuid.uuid4(), limit=0)

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: ConversationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_project(uuid.uuid4())


class TestGetOpenByUserAndProject:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: ConversationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_open_by_user_and_project(uuid.uuid4(), uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_invalid_limit(self, repo: ConversationRepository) -> None:
        with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
            await repo.get_open_by_user_and_project(uuid.uuid4(), uuid.uuid4(), limit=0)

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: ConversationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_open_by_user_and_project(uuid.uuid4(), uuid.uuid4())


class TestDataImmutability:

    def test_session_stored(
        self, repo: ConversationRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self) -> None:
        data = ConversationData(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            status="active",
            is_test=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.status = "ended"  # type: ignore[misc]
