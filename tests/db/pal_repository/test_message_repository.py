"""Tests for db.pal_repository.MessageRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only MessageData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.message import MessageData
from db.pal_repository.message import MessageRepository, _to_data
from db.tables.messages import Message


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> MessageRepository:
    return MessageRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_conversation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID, sample_conversation_id: uuid.UUID
) -> MagicMock:
    row = MagicMock(spec=Message)
    row.id = sample_id
    row.conversation_id = sample_conversation_id
    row.body = {"role": "user", "content": "hello"}
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = None
    return row


# ---------------------------------------------------------------------------
# _to_data
# ---------------------------------------------------------------------------


class TestToData:
    def test_converts_orm_row(self, sample_orm_row: MagicMock) -> None:
        data = _to_data(sample_orm_row)
        assert isinstance(data, MessageData)
        assert data.id == sample_orm_row.id
        assert data.conversation_id == sample_orm_row.conversation_id
        assert data.body == {"role": "user", "content": "hello"}
        assert data.created_at == sample_orm_row.created_at
        assert data.updated_at is None

    def test_converts_none_body(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.body = None
        data = _to_data(sample_orm_row)
        assert data.body == {}


# ---------------------------------------------------------------------------
# MessageData immutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_session_stored(
        self, repo: MessageRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self, sample_id: uuid.UUID) -> None:
        data = MessageData(
            id=sample_id,
            conversation_id=uuid.uuid4(),
            body={"role": "user", "content": "hello"},
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.id = uuid.uuid4()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: MessageRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)
        assert isinstance(data, MessageData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: MessageRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: MessageRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_by_conversation_id
# ---------------------------------------------------------------------------


class TestGetByConversationId:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: MessageRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_conversation_id(uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], MessageData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, repo: MessageRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_conversation_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: MessageRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_conversation_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_success(
        self,
        repo: MessageRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        mock_session.refresh = AsyncMock()
        record = MessageData(
            id=sample_id,
            conversation_id=sample_conversation_id,
            body={"role": "user", "content": "hello"},
        )

        with patch("db.pal_repository.message.Message") as MockMessage:
            MockMessage.return_value = sample_orm_row
            data = await repo.create(record)

        assert isinstance(data, MessageData)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_error_rolls_back(
        self,
        repo: MessageRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
        sample_conversation_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")
        record = MessageData(
            id=sample_id,
            conversation_id=sample_conversation_id,
            body={"role": "user", "content": "hello"},
        )

        with patch("db.pal_repository.message.Message") as MockMessage:
            MockMessage.return_value = sample_orm_row
            with pytest.raises(SQLAlchemyError):
                await repo.create(record)

        mock_session.rollback.assert_awaited_once()
