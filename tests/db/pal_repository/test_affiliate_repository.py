"""Tests for db.pal_repository.AffiliateRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.affiliate import AffiliateRepository


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> AffiliateRepository:
    return AffiliateRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = sample_id
    row.rewardful_id = "test"
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return row


class TestGetById:

    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: AffiliateRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_id(uuid.uuid4())
        assert data is not None

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: AffiliateRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: AffiliateRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_id(uuid.uuid4())


class TestGetByRewardfulId:

    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: AffiliateRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_rewardful_id("test")
        assert data is not None

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: AffiliateRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.get_by_rewardful_id("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: AffiliateRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_rewardful_id("test")


class TestListAffiliates:

    @pytest.mark.asyncio
    async def test_returns_list(
        self,
        repo: AffiliateRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        results = await repo.list_affiliates(10, 10)
        assert isinstance(results, list)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: AffiliateRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.list_affiliates()

    @pytest.mark.asyncio
    async def test_invalid_limit_zero(self, repo: AffiliateRepository) -> None:
        with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
            await repo.list_affiliates(limit=0)

    @pytest.mark.asyncio
    async def test_invalid_limit_too_large(self, repo: AffiliateRepository) -> None:
        with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
            await repo.list_affiliates(limit=1001)

    @pytest.mark.asyncio
    async def test_invalid_offset_negative(self, repo: AffiliateRepository) -> None:
        with pytest.raises(ValueError, match="offset must be >= 0"):
            await repo.list_affiliates(offset=-1)


class TestGetByRewardfulIds:

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_dict(
        self, repo: AffiliateRepository
    ) -> None:
        result = await repo.get_by_rewardful_ids([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_dict_keyed_by_rewardful_id(
        self,
        repo: AffiliateRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        result = await repo.get_by_rewardful_ids(["test"])
        assert "test" in result
        assert result["test"].rewardful_id == "test"

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: AffiliateRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_rewardful_ids(["test"])


class TestCreate:

    @pytest.mark.asyncio
    async def test_creates_and_returns_data(
        self,
        repo: AffiliateRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_session.refresh = AsyncMock(return_value=None)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(return_value=None)
        # After refresh, the row should be populated; simulate via side_effect
        mock_session.refresh.side_effect = lambda row: None
        # Patch Affiliate constructor via the execute path isn't needed;
        # create() builds the row directly. We mock session.add to capture it.
        captured_rows: list[MagicMock] = []

        def capture_add(row: MagicMock) -> None:
            # Populate the row with expected fields so _to_data works
            row.id = sample_orm_row.id
            row.rewardful_id = sample_orm_row.rewardful_id
            row.created_at = sample_orm_row.created_at
            row.updated_at = sample_orm_row.updated_at
            captured_rows.append(row)

        mock_session.add.side_effect = capture_add
        data = await repo.create("test")
        assert data is not None
        assert data.rewardful_id == "test"
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: AffiliateRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        with pytest.raises(RuntimeError, match="db error"):
            await repo.create("test")
        mock_session.rollback.assert_awaited_once()


class TestDelete:

    @pytest.mark.asyncio
    async def test_deletes_existing(
        self,
        repo: AffiliateRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock(return_value=None)
        result = await repo.delete(uuid.uuid4())
        assert result is True
        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_not_found_returns_false(
        self, repo: AffiliateRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        result = await repo.delete(uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self,
        repo: AffiliateRepository,
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
        self, repo: AffiliateRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session
