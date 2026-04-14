"""Tests for db.pal_repository.UserInvitationRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only UserInvitationData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.user_invitation import UserInvitationData
from db.pal_repository.user_invitation import UserInvitationRepository
from db.tables.user_invitation import UserInvitation

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> UserInvitationRepository:
    return UserInvitationRepository(mock_session)


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
    row = MagicMock(spec=UserInvitation)
    row.id = sample_id
    row.account_id = sample_account_id
    row.email = "user@example.com"
    row.account_role = "manager"
    row.project_ids = [uuid.uuid4(), uuid.uuid4()]
    row.invited_by = uuid.uuid4()
    row.invitation_token = "test-token-abc123"
    row.expires_at = datetime(2025, 7, 1, tzinfo=timezone.utc)
    row.accepted_at = None
    status_mock = MagicMock()
    status_mock.value = "pending"
    row.status = status_mock
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    """Lookup by primary key."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: UserInvitationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, UserInvitationData)
        assert data.id == sample_id
        assert data.status == "pending"
        assert data.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: UserInvitationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: UserInvitationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_by_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestGetByToken
# ---------------------------------------------------------------------------


class TestGetByToken:
    """Lookup by invitation token."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: UserInvitationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_token("test-token-abc123")

        assert isinstance(data, UserInvitationData)
        assert data.invitation_token == "test-token-abc123"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: UserInvitationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_token("nonexistent-token")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: UserInvitationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("timeout")

        with pytest.raises(RuntimeError, match="timeout"):
            await repo.get_by_token("any-token")


# ---------------------------------------------------------------------------
# TestListByAccountId
# ---------------------------------------------------------------------------


class TestListByAccountId:
    """List invitations for an account."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: UserInvitationRepository,
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
        assert isinstance(results[0], UserInvitationData)
        assert results[0].account_id == sample_account_id

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: UserInvitationRepository, mock_session: AsyncMock
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
        self, repo: UserInvitationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("error")

        with pytest.raises(RuntimeError, match="error"):
            await repo.list_by_account_id(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestListByEmail
# ---------------------------------------------------------------------------


class TestListByEmail:
    """List invitations for an email."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: UserInvitationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_email("user@example.com")

        assert len(results) == 1
        assert isinstance(results[0], UserInvitationData)
        assert results[0].email == "user@example.com"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(
        self, repo: UserInvitationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.list_by_email("nobody@example.com")
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: UserInvitationRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("error")

        with pytest.raises(RuntimeError, match="error"):
            await repo.list_by_email("user@example.com")


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new user invitation."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: UserInvitationRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        input_data = UserInvitationData(
            id=uuid.uuid4(),
            account_id=sample_account_id,
            email="new@example.com",
            account_role="staff",
            project_ids=(uuid.uuid4(), uuid.uuid4()),
            invited_by=uuid.uuid4(),
            invitation_token="new-token-xyz",
            expires_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
            status="pending",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: UserInvitationRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = RuntimeError("insert failed")

        input_data = UserInvitationData(
            id=uuid.uuid4(),
            account_id=sample_account_id,
            email="new@example.com",
            account_role="staff",
            invited_by=uuid.uuid4(),
            invitation_token="new-token-xyz",
            expires_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
            status="pending",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        with pytest.raises(RuntimeError, match="insert failed"):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Deleting a user invitation by ID."""

    @pytest.mark.asyncio
    async def test_delete_returns_data(
        self,
        repo: UserInvitationRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.delete(sample_id)

        assert isinstance(data, UserInvitationData)
        assert data.id == sample_id
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_returns_none_when_not_found(
        self, repo: UserInvitationRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.delete(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: UserInvitationRepository,
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
# TestProjectIdsImmutability
# ---------------------------------------------------------------------------


class TestProjectIdsImmutability:
    """project_ids uses tuple for true immutability in frozen dataclass."""

    def test_project_ids_is_tuple(self) -> None:
        project_ids = (uuid.uuid4(), uuid.uuid4())
        data = UserInvitationData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            email="user@example.com",
            account_role="staff",
            invited_by=uuid.uuid4(),
            invitation_token="token",
            expires_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
            status="pending",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            project_ids=project_ids,
        )
        assert isinstance(data.project_ids, tuple)
        assert len(data.project_ids) == 2

    def test_data_is_immutable(self) -> None:
        data = UserInvitationData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            email="user@example.com",
            account_role="staff",
            invited_by=uuid.uuid4(),
            invitation_token="token",
            expires_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
            status="pending",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.status = "changed"  # type: ignore[misc]
