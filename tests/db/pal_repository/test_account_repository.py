"""Tests for db.pal_repository.AccountRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only AccountData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.pal_repository.account import AccountRepository
from db.pal_repository.data_classes.account import AccountData
from db.tables.accounts import Account


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> AccountRepository:
    return AccountRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=Account)
    row.id = sample_id
    row.name = "test-account"
    row.status = MagicMock(value="active")
    row.onboarding_method = MagicMock(value="self_onboarding")
    row.contract_signed = True
    row.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    row.display_name = None
    row.icon_uri = None
    row.industry = None
    row.business_description = None
    row.business_faq = None
    row.business_promotions = None
    row.business_catalog = None
    row.business_others = None
    row.stripe_customer_id = None
    row.stripe_coupon_id = None
    row.current_subscription_id = None
    row.owner = None
    row.segment = None
    row.tier = None
    row.notes = None
    row.phone_number = None
    row.channels = []
    row.notification_preferences = {}
    row.notification_email = None
    row.updated_at = None
    return row


class TestGetById:
    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: AccountRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_id)

        assert isinstance(data, AccountData)
        assert data.id == sample_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: AccountRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_id(uuid.uuid4()) is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: AccountRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = RuntimeError("connection lost")

        with pytest.raises(RuntimeError, match="connection lost"):
            await repo.get_by_id(uuid.uuid4())


class TestGetByName:
    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: AccountRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_name("test-account")
        assert isinstance(data, AccountData)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: AccountRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_name("nonexistent") is None


class TestGetByStripeCustomerId:
    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: AccountRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_stripe_customer_id("cus_123")
        assert isinstance(data, AccountData)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: AccountRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        assert await repo.get_by_stripe_customer_id("cus_unknown") is None

    @pytest.mark.asyncio
    async def test_raises_on_duplicate_rows(
        self,
        repo: AccountRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row, sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Multiple accounts found"):
            await repo.get_by_stripe_customer_id("cus_duplicate")


class TestGetAllAccountNames:
    @pytest.mark.asyncio
    async def test_returns_tuples(
        self, repo: AccountRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_tuples = MagicMock()
        mock_tuples.all.return_value = [("acme", "Acme Corp")]
        mock_result.tuples.return_value = mock_tuples
        mock_session.execute.return_value = mock_result

        results = await repo.get_all_account_names()
        assert results == [("acme", "Acme Corp")]


class TestDataImmutability:
    def test_data_is_frozen(self) -> None:
        """Verify AccountData cannot be mutated after creation."""
        data = AccountData(
            id=uuid.uuid4(),
            name="test-account",
            status="active",
            onboarding_method="self_onboarding",
            contract_signed=True,
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(AttributeError):
            data.id = uuid.uuid4()  # type: ignore[misc]
