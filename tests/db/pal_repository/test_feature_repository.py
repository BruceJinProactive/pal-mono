"""Tests for db.pal_repository.FeatureRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.feature import FeatureData
from db.pal_repository.feature import FeatureRepository


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> FeatureRepository:
    return FeatureRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = sample_id
    row.feature = "dark_mode"
    row.identifier_type = MagicMock(value="account")
    row.identifier = "acct_123"
    row.enabled = True
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return row


class TestCheckEnablement:

    @pytest.mark.asyncio
    async def test_returns_true_when_enabled(
        self, repo: FeatureRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = True
        mock_session.execute.return_value = mock_result
        result = await repo.check_enablement("dark_mode", "account", "acct_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_disabled(
        self, repo: FeatureRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = False
        mock_session.execute.return_value = mock_result
        result = await repo.check_enablement("dark_mode", "account", "acct_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self, repo: FeatureRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.check_enablement("dark_mode", "account", "acct_123")
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: FeatureRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.check_enablement("dark_mode", "account", "acct_123")
        mock_session.rollback.assert_awaited_once()


class TestUpsert:

    @pytest.mark.asyncio
    async def test_upserts_and_returns_data(
        self,
        repo: FeatureRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock(return_value=None)

        data = await repo.upsert("dark_mode", "account", "acct_123", True)
        assert isinstance(data, FeatureData)
        assert data.feature == "dark_mode"
        assert data.enabled is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: FeatureRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.upsert("dark_mode", "account", "acct_123", True)
        mock_session.rollback.assert_awaited_once()


class TestDataImmutability:

    def test_session_stored(
        self, repo: FeatureRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self) -> None:
        data = FeatureData(
            id=uuid.uuid4(),
            feature="dark_mode",
            identifier_type="account",
            identifier="acct_123",
            enabled=True,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.enabled = False  # type: ignore[misc]
