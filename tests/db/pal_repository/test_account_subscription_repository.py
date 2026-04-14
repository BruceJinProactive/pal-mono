"""Tests for pal_repository.AccountSubscriptionRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only AccountSubscriptionData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.account_subscription import AccountSubscriptionRepository
from db.pal_repository.data_classes.account_subscription import AccountSubscriptionData
from db.pal_repository.data_classes.subscription_plan import SubscriptionPlanData
from db.tables.subscriptions import AccountSubscription, SubscriptionPlan
from db.tables.types import PaymentMethod, SubscriptionStatus, TargetTier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> AccountSubscriptionRepository:
    return AccountSubscriptionRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_external_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_account_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_plan_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_plan_row(sample_plan_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=SubscriptionPlan)
    row.id = sample_plan_id
    row.name = "Pro Plan"
    row.description = "Professional tier"
    row.tier = TargetTier.t2
    row.features_included = ["calls"]
    row.features_excluded = []
    row.call_quota = 1000
    row.order_quota = 500
    row.call_overage_charge = 5
    row.order_overage_charge = 10
    row.free_trial_days = 14
    row.credit_amount = 100
    row.monthly_fee = 99
    row.active = True
    row.sort_id = 2
    row.hidden = False
    row.created_at = NOW
    row.updated_at = NOW
    return row


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_external_id: uuid.UUID,
    sample_account_id: uuid.UUID,
    sample_plan_id: uuid.UUID,
    sample_plan_row: MagicMock,
) -> MagicMock:
    row = MagicMock(spec=AccountSubscription)
    row.id = sample_id
    row.external_id = sample_external_id
    row.version = 1
    row.account_id = sample_account_id
    row.subscription_plan_id = sample_plan_id
    row.stripe_product_id = "prod_abc"
    row.payment_method = PaymentMethod.autopay
    row.trial_start_date = None
    row.start_date = NOW
    row.end_date = None
    row.stripe_subscription_id = "sub_xyz"
    row.status = SubscriptionStatus.active
    row.recurring_credit_enabled = False
    row.recurring_credit_amount = None
    row.recurring_credit_frequency = None
    row.created_at = NOW
    row.updated_at = NOW
    row.subscription_plan = sample_plan_row
    return row


# ---------------------------------------------------------------------------
# TestCheckSubscriptionOverlap
# ---------------------------------------------------------------------------


class TestCheckSubscriptionOverlap:
    """Conservative overlap check — returns True on error."""

    @pytest.mark.asyncio
    async def test_returns_true_when_overlap_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.check_subscription_overlap(sample_account_id, NOW, None)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_overlap(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.check_subscription_overlap(sample_account_id, NOW, None)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_db_error(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        result = await repo.check_subscription_overlap(sample_account_id, NOW, None)
        assert result is True
        mock_session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_with_bounded_end_date(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        end = datetime(2025, 12, 31, tzinfo=timezone.utc)
        result = await repo.check_subscription_overlap(sample_account_id, NOW, end)
        assert result is False


# ---------------------------------------------------------------------------
# TestGetAccountSubscriptions
# ---------------------------------------------------------------------------


class TestGetAccountSubscriptions:
    """List active subscriptions with selectinload."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_account_subscriptions(sample_account_id)

        assert len(results) == 1
        assert isinstance(results[0], AccountSubscriptionData)
        assert isinstance(results[0].subscription_plan, SubscriptionPlanData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_account_subscriptions(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("timeout")

        with pytest.raises(SQLAlchemyError):
            await repo.get_account_subscriptions(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestGetByAccountAndExternalId
# ---------------------------------------------------------------------------


class TestGetByAccountAndExternalId:
    """Latest version lookup by account + external_id with selectinload."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_account_id: uuid.UUID,
        sample_external_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_account_and_external_id(
            sample_account_id, sample_external_id
        )

        assert isinstance(data, AccountSubscriptionData)
        assert data.external_id == sample_external_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_account_and_external_id(uuid.uuid4(), uuid.uuid4())
        assert data is None


# ---------------------------------------------------------------------------
# TestGetByExternalId
# ---------------------------------------------------------------------------


class TestGetByExternalId:
    """Latest version lookup by external_id with selectinload."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_external_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_external_id(sample_external_id)

        assert isinstance(data, AccountSubscriptionData)
        assert data.status == "active"
        assert data.payment_method == "autopay"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_external_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_external_id(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestGetByStripeSubscriptionId
# ---------------------------------------------------------------------------


class TestGetByStripeSubscriptionId:
    """Lookup by Stripe subscription ID (no selectinload)."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_stripe_subscription_id("sub_xyz")

        assert isinstance(data, AccountSubscriptionData)
        assert data.subscription_plan is None  # no selectinload

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_stripe_subscription_id("sub_nope")
        assert data is None


# ---------------------------------------------------------------------------
# TestGetActive
# ---------------------------------------------------------------------------


class TestGetActive:
    """Most recent valid subscription with selectinload."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_active(sample_account_id)

        assert isinstance(data, AccountSubscriptionData)
        assert isinstance(data.subscription_plan, SubscriptionPlanData)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_active(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_active(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestGetWithStripeId
# ---------------------------------------------------------------------------


class TestGetWithStripeId:
    """Subscriptions that have a stripe_subscription_id."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_account_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_with_stripe_id(sample_account_id)

        assert len(results) == 1
        assert isinstance(results[0], AccountSubscriptionData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_with_stripe_id(uuid.uuid4())
        assert results == []


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new account subscription."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        input_data = AccountSubscriptionData(
            id=uuid.uuid4(),
            external_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            subscription_plan_id=uuid.uuid4(),
            status="active",
            payment_method="autopay",
            start_date=NOW,
            created_at=NOW,
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        input_data = AccountSubscriptionData(
            id=uuid.uuid4(),
            external_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            subscription_plan_id=uuid.uuid4(),
            status="active",
            payment_method="autopay",
            start_date=NOW,
            created_at=NOW,
        )

        with pytest.raises(SQLAlchemyError):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdateStatus
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    """Updating subscription status."""

    @pytest.mark.asyncio
    async def test_update_returns_data(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_external_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.update_status(sample_external_id, "cancelled")

        assert isinstance(data, AccountSubscriptionData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.update_status(uuid.uuid4(), "cancelled")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_external_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("update failed")

        with pytest.raises(SQLAlchemyError):
            await repo.update_status(sample_external_id, "cancelled")
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------


class TestUpdate:
    """Generic update with **kwargs."""

    @pytest.mark.asyncio
    async def test_update_returns_data(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.update(sample_id, stripe_product_id="prod_new")

        assert isinstance(data, AccountSubscriptionData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.update(uuid.uuid4(), stripe_product_id="prod_new")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("update failed")

        with pytest.raises(SQLAlchemyError):
            await repo.update(sample_id, stripe_product_id="nope")
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdatePaymentMethod
# ---------------------------------------------------------------------------


class TestUpdatePaymentMethod:
    """Updating payment method."""

    @pytest.mark.asyncio
    async def test_update_returns_data(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.update_payment_method(sample_id, "invoice")

        assert isinstance(data, AccountSubscriptionData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.update_payment_method(uuid.uuid4(), "invoice")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: AccountSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.update_payment_method(sample_id, "invoice")
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """AccountSubscriptionData is a frozen dataclass."""

    def test_data_is_immutable(self) -> None:
        data = AccountSubscriptionData(
            id=uuid.uuid4(),
            external_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            subscription_plan_id=uuid.uuid4(),
            status="active",
            payment_method="autopay",
            start_date=NOW,
            created_at=NOW,
        )
        with pytest.raises(AttributeError):
            data.status = "changed"  # type: ignore[misc]

    def test_optional_fields_default_correctly(self) -> None:
        data = AccountSubscriptionData(
            id=uuid.uuid4(),
            external_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            subscription_plan_id=uuid.uuid4(),
            status="active",
            payment_method="autopay",
            start_date=NOW,
            created_at=NOW,
        )
        assert data.version is None
        assert data.stripe_product_id is None
        assert data.end_date is None
        assert data.recurring_credit_enabled is False
        assert data.subscription_plan is None
