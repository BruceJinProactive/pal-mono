"""Tests for db.pal_repository.LeadRepository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.lead import LeadData
from db.pal_repository.lead import LeadRepository, _to_data, _validate_mutable_fields


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> LeadRepository:
    return LeadRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock()
    row.id = sample_id
    row.status = MagicMock(value="active")
    row.contract_signed = False
    row.deleted = False
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.business_name = "Test Biz"
    row.business_address = None
    row.logo_uri = None
    row.segment = MagicMock(value="smb")
    row.tier = MagicMock(value="gold")
    row.pos = None
    row.channels = ["web", "phone"]
    row.account_id = uuid.uuid4()
    row.owner = None
    row.hubspot_record_id = None
    row.notes = None
    row.updated_at = datetime(2025, 6, 2, tzinfo=timezone.utc)
    return row


# ---------------------------------------------------------------------------
# _to_data
# ---------------------------------------------------------------------------


class TestToData:
    def test_converts_orm_row_to_lead_data(self, sample_orm_row: MagicMock) -> None:
        data = _to_data(sample_orm_row)
        assert isinstance(data, LeadData)
        assert data.id == sample_orm_row.id
        assert data.status == "active"
        assert data.contract_signed is False
        assert data.deleted is False
        assert data.business_name == "Test Biz"
        assert data.segment == "smb"
        assert data.tier == "gold"
        assert data.channels == ("web", "phone")
        assert data.updated_at == sample_orm_row.updated_at

    def test_converts_none_segment_and_tier(self, sample_orm_row: MagicMock) -> None:
        sample_orm_row.segment = None
        sample_orm_row.tier = None
        sample_orm_row.channels = None
        data = _to_data(sample_orm_row)
        assert data.segment is None
        assert data.tier is None
        assert data.channels == ()


# ---------------------------------------------------------------------------
# _validate_mutable_fields
# ---------------------------------------------------------------------------


class TestValidateMutableFields:
    def test_accepts_valid_fields(self) -> None:
        _validate_mutable_fields({"business_name": "x", "status": "active"}, "set")

    def test_rejects_invalid_field(self) -> None:
        with pytest.raises(ValueError, match="Cannot set field: bad"):
            _validate_mutable_fields({"bad": "x"}, "set")

    def test_action_appears_in_message(self) -> None:
        with pytest.raises(ValueError, match="Cannot update field"):
            _validate_mutable_fields({"bad": "x"}, "update")


# ---------------------------------------------------------------------------
# LeadData immutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    def test_session_stored(
        self, repo: LeadRepository, mock_session: AsyncMock
    ) -> None:
        assert repo.session is mock_session

    def test_data_is_frozen(self, sample_id: uuid.UUID) -> None:
        data = LeadData(
            id=sample_id,
            status="active",
            contract_signed=False,
            deleted=False,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.status = "closed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


class TestGetById:
    @pytest.mark.asyncio
    async def test_found(
        self,
        repo: LeadRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is not None
        assert isinstance(data, LeadData)
        assert data.id == sample_orm_row.id

    @pytest.mark.asyncio
    async def test_not_found(
        self, repo: LeadRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_error_rolls_back(
        self, repo: LeadRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_create_with_valid_fields(
        self,
        repo: LeadRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_session.refresh = AsyncMock()

        with patch("db.pal_repository.lead.Lead") as MockLead:
            MockLead.return_value = sample_orm_row
            data = await repo.create(business_name="New Biz")

        assert isinstance(data, LeadData)
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_field(
        self, repo: LeadRepository, mock_session: AsyncMock
    ) -> None:
        with pytest.raises(ValueError, match="Cannot set field"):
            await repo.create(invalid_field="bad")
        mock_session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_error_rolls_back(
        self,
        repo: LeadRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        with patch("db.pal_repository.lead.Lead") as MockLead:
            MockLead.return_value = sample_orm_row
            with pytest.raises(SQLAlchemyError):
                await repo.create(business_name="New Biz")

        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_found(
        self,
        repo: LeadRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.update(sample_id, business_name="Updated Biz")
        assert data is not None
        assert isinstance(data, LeadData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_not_found(
        self, repo: LeadRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.update(uuid.uuid4(), business_name="No One")
        assert result is None
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_rejects_invalid_field(
        self, repo: LeadRepository, mock_session: AsyncMock
    ) -> None:
        with pytest.raises(ValueError, match="Cannot update field"):
            await repo.update(uuid.uuid4(), bad_field="nope")
        mock_session.execute.assert_not_awaited()
        mock_session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_error_rolls_back(
        self,
        repo: LeadRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("commit failed")

        with pytest.raises(SQLAlchemyError):
            await repo.update(uuid.uuid4(), business_name="Fail")
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_found(
        self,
        repo: LeadRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        await repo.delete(uuid.uuid4())
        assert sample_orm_row.deleted is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(
        self, repo: LeadRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        await repo.delete(uuid.uuid4())
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_error_rolls_back(
        self, repo: LeadRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("db error")
        with pytest.raises(SQLAlchemyError):
            await repo.delete(uuid.uuid4())
        mock_session.rollback.assert_awaited_once()
