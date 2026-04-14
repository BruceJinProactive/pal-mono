"""Tests for pal_repository.ProjectSubscriptionRepository.

Validates the async repository: ORM objects stay inside the
repository layer and only ProjectSubscriptionData instances are returned.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from db.pal_repository.data_classes.project_subscription import ProjectSubscriptionData
from db.pal_repository.project_subscription import ProjectSubscriptionRepository
from db.tables.subscriptions import ProjectSubscription
from db.tables.types import PaymentMethod, SubscriptionStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def repo(mock_session: AsyncMock) -> ProjectSubscriptionRepository:
    return ProjectSubscriptionRepository(mock_session)


@pytest.fixture
def sample_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_project_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_subscription_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_external_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_orm_row(
    sample_id: uuid.UUID,
    sample_project_id: uuid.UUID,
    sample_subscription_id: uuid.UUID,
    sample_external_id: uuid.UUID,
) -> MagicMock:
    row = MagicMock(spec=ProjectSubscription)
    row.id = sample_id
    row.external_id = sample_external_id
    row.version = 1
    row.project_id = sample_project_id
    row.subscription_id = sample_subscription_id
    row.subscription_plan_id = uuid.uuid4()
    row.stripe_product_id = "prod_abc"
    row.stripe_subscription_id = "sub_xyz"
    row.payment_method = PaymentMethod.autopay
    row.base_price_id = None
    row.call_price_id = "price_call"
    row.order_price_id = "price_order"
    row.trial_start_date = None
    row.start_date = NOW
    row.end_date = None
    row.status = SubscriptionStatus.active
    row.deleted = False
    row.recurring_credit_enabled = False
    row.recurring_credit_amount = None
    row.recurring_credit_frequency = None
    row.created_at = NOW
    row.updated_at = NOW
    return row


# ---------------------------------------------------------------------------
# TestGetBySubscriptionId
# ---------------------------------------------------------------------------


class TestGetBySubscriptionId:
    """List non-deleted project subscriptions for a subscription."""

    @pytest.mark.asyncio
    async def test_returns_list_of_data(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_subscription_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [sample_orm_row]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_subscription_id(sample_subscription_id)

        assert len(results) == 1
        assert isinstance(results[0], ProjectSubscriptionData)

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        results = await repo.get_by_subscription_id(uuid.uuid4())
        assert results == []

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("timeout")

        with pytest.raises(SQLAlchemyError):
            await repo.get_by_subscription_id(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestGet
# ---------------------------------------------------------------------------


class TestGet:
    """Lookup by project + subscription IDs."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_subscription_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get(sample_project_id, sample_subscription_id)

        assert isinstance(data, ProjectSubscriptionData)
        assert data.project_id == sample_project_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get(uuid.uuid4(), uuid.uuid4())
        assert data is None


# ---------------------------------------------------------------------------
# TestGetByProjectId
# ---------------------------------------------------------------------------


class TestGetByProjectId:
    """First non-deleted subscription for a project."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_project_id(sample_project_id)

        assert isinstance(data, ProjectSubscriptionData)

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_project_id(uuid.uuid4())
        assert data is None


# ---------------------------------------------------------------------------
# TestGetByExternalId
# ---------------------------------------------------------------------------


class TestGetByExternalId:
    """Latest version lookup by external_id."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectSubscriptionRepository,
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

        assert isinstance(data, ProjectSubscriptionData)
        assert data.external_id == sample_external_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_external_id(uuid.uuid4())
        assert data is None


# ---------------------------------------------------------------------------
# TestGetActive
# ---------------------------------------------------------------------------


class TestGetActive:
    """Most recent valid subscription for a project."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_active(sample_project_id)

        assert isinstance(data, ProjectSubscriptionData)
        assert data.status == "active"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: ProjectSubscriptionRepository,
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
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("error")

        with pytest.raises(SQLAlchemyError):
            await repo.get_active(uuid.uuid4())
        mock_session.rollback.assert_not_awaited()


# ---------------------------------------------------------------------------
# TestCheckSubscriptionOverlap
# ---------------------------------------------------------------------------


class TestCheckSubscriptionOverlap:
    """Conservative overlap check — returns True on error."""

    @pytest.mark.asyncio
    async def test_returns_true_when_overlap_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.check_subscription_overlap(sample_project_id, NOW, None)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_overlap(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.check_subscription_overlap(sample_project_id, NOW, None)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_db_error(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_session.execute.side_effect = SQLAlchemyError("connection lost")

        result = await repo.check_subscription_overlap(sample_project_id, NOW, None)
        assert result is True
        mock_session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_with_bounded_end_date(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        end = datetime(2025, 12, 31, tzinfo=timezone.utc)
        result = await repo.check_subscription_overlap(sample_project_id, NOW, end)
        assert result is False


# ---------------------------------------------------------------------------
# TestGetByStripeId
# ---------------------------------------------------------------------------


class TestGetByStripeId:
    """Lookup by Stripe subscription ID."""

    @pytest.mark.asyncio
    async def test_returns_data_when_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_stripe_id("sub_xyz")

        assert isinstance(data, ProjectSubscriptionData)
        assert data.stripe_subscription_id == "sub_xyz"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.get_by_stripe_id("sub_nope")
        assert data is None


# ---------------------------------------------------------------------------
# TestCreate
# ---------------------------------------------------------------------------


class TestCreate:
    """Creating a new project subscription."""

    @pytest.mark.asyncio
    async def test_create_commits(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
        sample_subscription_id: uuid.UUID,
    ) -> None:
        await repo.create(sample_project_id, sample_subscription_id)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_with_stripe_product(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
        sample_subscription_id: uuid.UUID,
    ) -> None:
        await repo.create(
            sample_project_id, sample_subscription_id, stripe_product_id="prod_abc"
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_raises_on_db_error(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
        sample_subscription_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        with pytest.raises(SQLAlchemyError):
            await repo.create(sample_project_id, sample_subscription_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestCreateWithPrices
# ---------------------------------------------------------------------------


class TestCreateWithPrices:
    """Creating a project subscription with price IDs."""

    @pytest.mark.asyncio
    async def test_create_with_prices_commits(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
        sample_subscription_id: uuid.UUID,
    ) -> None:
        await repo.create_with_prices(
            sample_project_id,
            sample_subscription_id,
            call_price_id="price_call",
            order_price_id="price_order",
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_with_prices_raises_on_db_error(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_project_id: uuid.UUID,
        sample_subscription_id: uuid.UUID,
    ) -> None:
        mock_session.commit.side_effect = SQLAlchemyError("insert failed")

        with pytest.raises(SQLAlchemyError):
            await repo.create_with_prices(sample_project_id, sample_subscription_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestSoftDelete
# ---------------------------------------------------------------------------


class TestSoftDelete:
    """Soft-deleting a project subscription."""

    @pytest.mark.asyncio
    async def test_returns_true_on_success(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_subscription_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.soft_delete(sample_project_id, sample_subscription_id)

        assert result is True
        assert sample_orm_row.deleted is True
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.soft_delete(uuid.uuid4(), uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_project_id: uuid.UUID,
        sample_subscription_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result
        mock_session.commit.side_effect = SQLAlchemyError("delete failed")

        with pytest.raises(SQLAlchemyError):
            await repo.soft_delete(sample_project_id, sample_subscription_id)
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdate
# ---------------------------------------------------------------------------


class TestUpdate:
    """Generic update with **kwargs."""

    @pytest.mark.asyncio
    async def test_update_returns_data(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
        sample_orm_row: MagicMock,
        sample_id: uuid.UUID,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = sample_orm_row
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.update(sample_id, call_price_id="price_new")

        assert isinstance(data, ProjectSubscriptionData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: ProjectSubscriptionRepository,
        mock_session: AsyncMock,
    ) -> None:
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        data = await repo.update(uuid.uuid4(), call_price_id="price_new")
        assert data is None

    @pytest.mark.asyncio
    async def test_raises_on_db_error(
        self,
        repo: ProjectSubscriptionRepository,
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
            await repo.update(sample_id, call_price_id="nope")
        mock_session.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# TestUpdateStatus
# ---------------------------------------------------------------------------


class TestUpdateStatus:
    """Updating subscription status."""

    @pytest.mark.asyncio
    async def test_update_returns_data(
        self,
        repo: ProjectSubscriptionRepository,
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

        assert isinstance(data, ProjectSubscriptionData)
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(
        self,
        repo: ProjectSubscriptionRepository,
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
        repo: ProjectSubscriptionRepository,
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
# TestDataImmutability
# ---------------------------------------------------------------------------


class TestDataImmutability:
    """ProjectSubscriptionData is a frozen dataclass."""

    def test_data_is_immutable(self) -> None:
        data = ProjectSubscriptionData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            subscription_id=uuid.uuid4(),
            deleted=False,
            created_at=NOW,
        )
        with pytest.raises(AttributeError):
            data.status = "changed"  # type: ignore[misc]

    def test_optional_fields_default_correctly(self) -> None:
        data = ProjectSubscriptionData(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            subscription_id=uuid.uuid4(),
            deleted=False,
            created_at=NOW,
        )
        assert data.external_id is None
        assert data.version is None
        assert data.stripe_product_id is None
        assert data.payment_method is None
        assert data.status is None
        assert data.recurring_credit_enabled is False
