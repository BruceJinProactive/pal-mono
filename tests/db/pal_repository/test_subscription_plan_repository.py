"""Tests for pal_repository.SubscriptionPlanRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only SubscriptionPlanData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.subscription_plan import SubscriptionPlanData
from db.pal_repository.subscription_plan import SubscriptionPlanRepository
from db.tables.subscriptions import SubscriptionPlan
from db.tables.types import TargetTier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> SubscriptionPlanRepository:
    return SubscriptionPlanRepository(mock_session)


@pytest.fixture
def sample_plan_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(sample_plan_id: uuid.UUID) -> MagicMock:
    row = MagicMock(spec=SubscriptionPlan)
    row.id = sample_plan_id
    row.name = "Pro Plan"
    row.description = "Professional tier"
    row.tier = TargetTier.t2
    row.features_included = ["calls", "orders"]
    row.features_excluded = ["analytics"]
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


# ---------------------------------------------------------------------------
# TestGetById
# ---------------------------------------------------------------------------


class TestGetById:
    """Lookup by primary key (active plans only)."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_plan_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(sample_plan_id)

        assert isinstance(data, SubscriptionPlanData)
        assert data.id == sample_plan_id
        assert data.name == "Pro Plan"
        assert data.tier == "t2"
        assert data.features_included == ["calls", "orders"]

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self, repo: SubscriptionPlanRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_id(uuid.uuid4())
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: SubscriptionPlanRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_id(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestGetAll
# ---------------------------------------------------------------------------


class TestGetAll:
    """List all active plans, optionally filtered by hidden."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_all()

        assert len(results) == 1
        assert isinstance(results[0], SubscriptionPlanData)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none(
        self, repo: SubscriptionPlanRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_all(hidden=False)
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self, repo: SubscriptionPlanRepository, mock_session: AsyncMock
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("timeout")

        with pytest.raises(SQLAlchemyError):
            await repo.get_all()
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestHasActiveAccountSubscriptions
# ---------------------------------------------------------------------------


class TestHasActiveAccountSubscriptions:
    """Conservative check — returns True on error."""

    @pytest.mark.asyncio
    async def test_returns_true_when_active_exists(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
        sample_plan_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        assert await repo.has_active_account_subscriptions(sample_plan_id) is True

    @pytest.mark.asyncio
    async def test_returns_false_when_none_exist(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
        sample_plan_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        assert await repo.has_active_account_subscriptions(sample_plan_id) is False

    @pytest.mark.asyncio
    async def test_returns_true_on_db_error(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
        sample_plan_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        result = await repo.has_active_account_subscriptions(sample_plan_id)
        assert result is True
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new subscription plan."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
    ) -> None:
        input_data = SubscriptionPlanData(
            id=uuid.uuid4(),
            name="Basic",
            tier="t1",
            active=True,
            created_at=NOW,
        )

        await repo.create(input_data)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        input_data = SubscriptionPlanData(
            id=uuid.uuid4(),
            name="Basic",
            tier="t1",
            active=True,
            created_at=NOW,
        )

        with pytest.raises(SQLAlchemyError):
            await repo.create(input_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------


class TestUpdate:
    """Updating subscription plan details."""

    @pytest.mark.asyncio
    async def test_update_returns_data(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_plan_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        update_data = SubscriptionPlanData(
            id=sample_plan_id,
            name="Updated Plan",
            tier="t3",
            active=True,
            created_at=NOW,
        )

        data = await repo.update(sample_plan_id, update_data)

        assert isinstance(data, SubscriptionPlanData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_raises_value_error_when_not_found(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        update_data = SubscriptionPlanData(
            id=uuid.uuid4(),
            name="Nope",
            tier="t1",
            active=True,
            created_at=NOW,
        )

        with pytest.raises(ValueError, match="not found"):
            await repo.update(uuid.uuid4(), update_data)

    @pytest.mark.asyncio
    async def test_update_raises_on_db_error(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_plan_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("update failed")

        update_data = SubscriptionPlanData(
            id=sample_plan_id,
            name="Fail",
            tier="t1",
            active=True,
            created_at=NOW,
        )

        with pytest.raises(SQLAlchemyError):
            await repo.update(sample_plan_id, update_data)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDelete
# ---------------------------------------------------------------------------


class TestDelete:
    """Hard-deleting a subscription plan."""

    @pytest.mark.asyncio
    async def test_delete_commits(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_plan_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result

        await repo.delete(sample_plan_id)

        mock_session.delete.assert_awaited_once_with(sample_orm_row)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_raises_value_error_when_not_found(
        self, repo: SubscriptionPlanRepository, mock_session: AsyncMock
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await repo.delete(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_delete_raises_on_db_error(
        self,
        repo: SubscriptionPlanRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_plan_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_orm_row
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("delete failed")

        with pytest.raises(SQLAlchemyError):
            await repo.delete(sample_plan_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """SubscriptionPlanData is a frozen dataclass — mutations are disallowed."""

    def test_data_is_immutable(self) -> None:
        data = SubscriptionPlanData(
            id=uuid.uuid4(),
            name="Test",
            tier="t1",
            active=True,
            created_at=NOW,
        )
        with pytest.raises(AttributeError):
            data.name = "changed"  # type: ignore[misc]

    def test_optional_fields_default_to_none(self) -> None:
        data = SubscriptionPlanData(
            id=uuid.uuid4(),
            name="Test",
            tier="t1",
            active=True,
            created_at=NOW,
        )
        assert data.description is None
        assert data.call_quota is None
        assert data.order_quota is None
        assert data.monthly_fee is None
        assert data.sort_id is None
        assert data.updated_at is None

    def test_list_fields_default_to_empty(self) -> None:
        data = SubscriptionPlanData(
            id=uuid.uuid4(),
            name="Test",
            tier="t1",
            active=True,
            created_at=NOW,
        )
        assert data.features_included == []
        assert data.features_excluded == []
