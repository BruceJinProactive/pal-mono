"""Tests for db.pal_repository.CampaignRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.campaign import CampaignRepository, _msg_to_data
from db.pal_repository.data_classes.campaign import CampaignData, CampaignMessageData


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> CampaignRepository:
    return CampaignRepository(mock_session)


@pytest.fixture
def sample_orm_row() -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.account_id = uuid.uuid4()
    row.name = "Test Campaign"
    row.message = "Hello!"
    row.channel = MagicMock(value="sms")
    row.internal_recipient = False
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.updated_at = None
    return row


@pytest.fixture
def sample_msg_orm_row() -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.campaign_id = uuid.uuid4()
    row.recipient = "+15551234567"
    row.status = MagicMock(value="sent")
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.error_detail = None
    row.updated_at = None
    return row


class TestGetById:

    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: CampaignRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        data = await repo.get_by_id(uuid.uuid4())
        assert isinstance(data, CampaignData)
        assert data.channel == "sms"

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: CampaignRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: CampaignRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_id(uuid.uuid4())


class TestGetByAccountId:

    @pytest.mark.asyncio
    async def test_returns_tuple(
        self,
        repo: CampaignRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1
        mock_data_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_data_result.scalars.return_value = mock_scalars
        mock_session.execute.side_effect = [mock_count_result, mock_data_result]

        items, total = await repo.get_by_account_id(uuid.uuid4())
        assert isinstance(items, list)
        assert len(items) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_exception_propagates(
        self, repo: CampaignRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("db error")
        with pytest.raises(RuntimeError, match="db error"):
            await repo.get_by_account_id(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_invalid_limit(self, repo: CampaignRepository) -> None:
        with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
            await repo.get_by_account_id(uuid.uuid4(), limit=0)
        with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
            await repo.get_by_account_id(uuid.uuid4(), limit=1001)

    @pytest.mark.asyncio
    async def test_invalid_skip(self, repo: CampaignRepository) -> None:
        with pytest.raises(ValueError, match="skip must be >= 0"):
            await repo.get_by_account_id(uuid.uuid4(), skip=-1)


class TestCreate:

    @pytest.mark.asyncio
    async def test_creates_and_returns_data(
        self,
        repo: CampaignRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(return_value=None)

        def populate_on_refresh(row: MagicMock) -> None:
            row.id = sample_orm_row.id
            row.account_id = sample_orm_row.account_id
            row.name = sample_orm_row.name
            row.message = sample_orm_row.message
            row.channel = sample_orm_row.channel
            row.internal_recipient = sample_orm_row.internal_recipient
            row.created_at = sample_orm_row.created_at
            row.updated_at = sample_orm_row.updated_at

        mock_session.refresh = AsyncMock(side_effect=populate_on_refresh)

        record = CampaignData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            name="Test",
            message="Hello!",
            channel="sms",
            internal_recipient=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        data = await repo.create(record)
        assert data is not None
        assert data.name == "Test Campaign"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exception_rolls_back(
        self, repo: CampaignRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=RuntimeError("db error"))
        mock_session.rollback = AsyncMock(return_value=None)
        record = CampaignData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            name="Test",
            message="Hello!",
            channel="sms",
            internal_recipient=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(RuntimeError, match="db error"):
            await repo.create(record)
        mock_session.rollback.assert_awaited_once()


class TestMsgToData:

    def test_converts_message_row(self, sample_msg_orm_row: MagicMock) -> None:
        data = _msg_to_data(sample_msg_orm_row)
        assert isinstance(data, CampaignMessageData)
        assert data.recipient == "+15551234567"
        assert data.status == "sent"
        assert data.error_detail is None


class TestDataImmutability:

    def test_session_stored(
        self, repo: CampaignRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_campaign_data_is_frozen(self) -> None:
        data = CampaignData(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            name="Test",
            message="Hello!",
            channel="sms",
            internal_recipient=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]

    def test_campaign_message_data_is_frozen(self) -> None:
        data = CampaignMessageData(
            id=uuid.uuid4(),
            campaign_id=uuid.uuid4(),
            recipient="+15551234567",
            status="sent",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.status = "failed"  # type: ignore[misc]
