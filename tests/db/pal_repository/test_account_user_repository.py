"""Tests for db.pal_repository.AccountUserRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.account_user import AccountUserRepository
from db.pal_repository.data_classes.account_user import AccountUserData


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> AccountUserRepository:
    return AccountUserRepository(mock_session)


@pytest.fixture
def sample_orm_row() -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.account_id = uuid.uuid4()
    row.user_id = uuid.uuid4()
    row.status = MagicMock(value="active")
    row.added_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.name = "Test"
    row.email = "test@example.com"
    row.added_by = None
    return row


class TestGetByUserAndAccount:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_user_and_account(uuid.uuid4(), uuid.uuid4())
        assert isinstance(data, AccountUserData)

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        assert await repo.get_by_user_and_account(uuid.uuid4(), uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")
        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_by_user_and_account(uuid.uuid4(), uuid.uuid4())


class TestGetByEmailAndAccount:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_email_and_account("test@example.com", uuid.uuid4())
        assert isinstance(data, AccountUserData)

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        assert (
            await repo.get_by_email_and_account("nobody@example.com", uuid.uuid4())
            is None
        )

    @pytest.mark.asyncio
    async def test_normalizes_email(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        # Should not raise even with whitespace/mixed case
        await repo.get_by_email_and_account("  Test@Example.COM  ", uuid.uuid4())
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")
        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_by_email_and_account("x@y.com", uuid.uuid4())


class TestGetUsersForAccount:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_users_for_account(uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_with_status_filter(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_users_for_account(uuid.uuid4(), status="active")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")
        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_users_for_account(uuid.uuid4())


class TestGetAccountsForUser:
    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_accounts_for_user(uuid.uuid4())
        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_with_status_filter(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.get_accounts_for_user(uuid.uuid4(), status="active")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")
        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_accounts_for_user(uuid.uuid4())


class TestIsMember:
    @pytest.mark.asyncio
    async def test_returns_true_when_active(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_session.execute.return_value = mock_result
        result = await repo.is_member(uuid.uuid4(), uuid.uuid4())
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_member(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_session.execute.return_value = mock_result
        result = await repo.is_member(uuid.uuid4(), uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_scalar_none(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.is_member(uuid.uuid4(), uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")
        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.is_member(uuid.uuid4(), uuid.uuid4())


class TestCreate:
    def _mock_no_existing(self, mock_session: AsyncMock) -> None:
        """Helper: mock get_by_user_and_account returning None (no existing)."""
        mock_lookup = MagicMock()
        mock_lookup_scalars = MagicMock()
        mock_lookup_scalars.first.return_value = None
        mock_lookup.scalars.return_value = mock_lookup_scalars
        # First execute call is the existence check, second is unused here
        mock_session.execute.return_value = mock_lookup

    @pytest.mark.asyncio
    async def test_returns_existing_when_already_member(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        """Idempotent: returns existing membership without creating."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        mock_session.add = MagicMock()
        data = await repo.create(
            account_id=sample_orm_row.account_id,
            user_id=sample_orm_row.user_id,
            email="test@example.com",
            name="Test",
        )
        assert isinstance(data, AccountUserData)
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_and_returns_data(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        self._mock_no_existing(mock_session)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        async def refresh_side_effect(row: MagicMock) -> None:
            row.id = sample_orm_row.id
            row.account_id = sample_orm_row.account_id
            row.user_id = sample_orm_row.user_id
            row.status = sample_orm_row.status
            row.added_at = sample_orm_row.added_at
            row.created_at = sample_orm_row.created_at
            row.updated_at = sample_orm_row.updated_at
            row.name = sample_orm_row.name
            row.email = sample_orm_row.email
            row.added_by = sample_orm_row.added_by

        mock_session.refresh = AsyncMock(side_effect=refresh_side_effect)
        data = await repo.create(
            account_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            email="Test@Example.COM",
            name="Test",
        )
        assert isinstance(data, AccountUserData)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_normalizes_email_on_create(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        self._mock_no_existing(mock_session)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        async def refresh_side_effect(row: MagicMock) -> None:
            row.id = sample_orm_row.id
            row.account_id = sample_orm_row.account_id
            row.user_id = sample_orm_row.user_id
            row.status = sample_orm_row.status
            row.added_at = sample_orm_row.added_at
            row.created_at = sample_orm_row.created_at
            row.updated_at = sample_orm_row.updated_at
            row.name = sample_orm_row.name
            row.email = "test@example.com"
            row.added_by = sample_orm_row.added_by

        mock_session.refresh = AsyncMock(side_effect=refresh_side_effect)
        await repo.create(
            account_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            email="  Test@Example.COM  ",
            name="Test",
        )
        # Verify the row was added with normalized email
        added_row = mock_session.add.call_args[0][0]
        assert added_row.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_rolls_back_on_error(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        self._mock_no_existing(mock_session)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock()
        with pytest.raises(RuntimeError, match="db error"):
            await repo.create(
                account_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                email="test@example.com",
                name="Test",
            )
        mock_session.rollback.assert_awaited_once()


class TestUpdateStatus:
    @pytest.mark.asyncio
    async def test_updates_and_returns_data(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        data = await repo.update_status(uuid.uuid4(), uuid.uuid4(), "deactivated")
        assert isinstance(data, AccountUserData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.update_status(uuid.uuid4(), uuid.uuid4(), "deactivated")
        assert result is None

    @pytest.mark.asyncio
    async def test_rolls_back_on_error(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock()

        with pytest.raises(RuntimeError, match="db error"):
            await repo.update_status(uuid.uuid4(), uuid.uuid4(), "deactivated")
        mock_session.rollback.assert_awaited_once()


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_and_returns_true(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()

        result = await repo.delete(uuid.uuid4(), uuid.uuid4())
        assert result is True
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self, repo: AccountUserRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.delete(uuid.uuid4(), uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_rolls_back_on_error(
        self,
        repo: AccountUserRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock()

        with pytest.raises(RuntimeError, match="db error"):
            await repo.delete(uuid.uuid4(), uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:
    def test_data_is_frozen(self) -> None:
        """Verify AccountUserData cannot be mutated after creation."""
        data = AccountUserData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            status="active",
            added_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.id = uuid.uuid4()  # type: ignore[misc]
