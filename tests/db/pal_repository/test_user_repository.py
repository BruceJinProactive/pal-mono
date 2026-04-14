"""Tests for db.pal_repository.UserRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only UserData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.user import UserData
from db.pal_repository.user import UserRepository
from db.tables.users import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> UserRepository:
    return UserRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_account_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_account_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=User)
    row.id = sample_id
    row.account_id = sample_account_id
    row.raw_config = {"lang": "en"}
    row.channel_identifiers = ["+1234567890"]
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
        repo: UserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, UserData)
        assert data.id == sample_id
        assert data.channel_identifiers == ("+1234567890",)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: UserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: UserRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByAccountId
# ---------------------------------------------------------------------------


class TestListByAccountId:
    """List users for an account."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: UserRepository,
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
        assert isinstance(results[0], UserData)
        assert results[0].account_id == sample_account_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: UserRepository, mock_session: AsyncMock
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
        self, repo: UserRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("timeout")

        with pytest.raises(RuntimeError, match="timeout"):
            await repo.list_by_account_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByChannelIdentifier
# ---------------------------------------------------------------------------


class TestGetByChannelIdentifier:
    """Lookup by channel identifier."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: UserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_channel_identifier("+1234567890")

        assert isinstance(data, UserData)
        assert "+1234567890" in data.channel_identifiers  # type: ignore[operator]

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: UserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_channel_identifier("+0000000000")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: UserRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("error")

        with pytest.raises(RuntimeError, match="error"):
            await repo.get_by_channel_identifier("+1234567890")


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new user."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: UserRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        input_data = UserData(
            id=uuid.uuid4(),
            account_id=sample_account_id,
            raw_config={"lang": "en"},
            channel_identifiers=("+1234567890",),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: UserRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = RuntimeError("insert failed")

        input_data = UserData(
            id=uuid.uuid4(),
            account_id=sample_account_id,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(RuntimeError, match="insert failed"):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a user by ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: UserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_id)

        assert isinstance(data, UserData)
        assert data.id == sample_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: UserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: UserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = RuntimeError("delete failed")

        with pytest.raises(RuntimeError, match="delete failed"):
            await repo.delete(sample_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestChannelIdentifiersImmutability
# ---------------------------------------------------------------------------


class TestChannelIdentifiersImmutability:
    """channel_identifiers uses tuple for true immutability."""

    def test_channel_identifiers_is_tuple(self) -> None:
        data = UserData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            channel_identifiers=("+1234567890", "+0987654321"),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        assert isinstance(data.channel_identifiers, tuple)
        assert len(data.channel_identifiers) == 2

    def test_list_normalized_to_tuple(self) -> None:
        data = UserData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            channel_identifiers=["+1234567890"],  # type: ignore[arg-type]
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        assert isinstance(data.channel_identifiers, tuple)

    def test_data_is_immutable(self) -> None:
        data = UserData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.account_id = uuid.uuid4()  # type: ignore[misc]
