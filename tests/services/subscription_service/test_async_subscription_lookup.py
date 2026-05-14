"""Tests for async pal-repository subscription lookup helpers."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest

from db.pal_repository.data_classes.account_subscription import AccountSubscriptionData
from db.pal_repository.data_classes.project_subscription import ProjectSubscriptionData
from db.pal_repository.data_classes.subscription_plan import SubscriptionPlanData
from services.subscription_service import _subscription


@pytest.fixture
def account_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def external_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def async_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def subscription_data(
    account_id: uuid.UUID,
    external_id: uuid.UUID,
) -> AccountSubscriptionData:
    return AccountSubscriptionData(
        id=uuid.uuid4(),
        external_id=external_id,
        account_id=account_id,
        subscription_plan_id=uuid.uuid4(),
        status="active",
        payment_method="autopay",
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
def subscription_plan_data() -> SubscriptionPlanData:
    return SubscriptionPlanData(
        id=uuid.uuid4(),
        name="Pro Plan",
        tier="t2",
        active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        call_quota=100,
        order_quota=50,
        call_overage_charge=5,
        order_overage_charge=10,
        monthly_fee=5000,
    )


class TestGetAccountSubscriptionDataAsync:
    """Service helper delegates to the async pal repository."""

    @pytest.mark.asyncio
    async def test_uses_pal_repository(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        subscription_data: AccountSubscriptionData,
    ) -> None:
        mock_repo = MagicMock()
        mock_repo.get_by_account_and_external_id = AsyncMock(
            return_value=subscription_data
        )
        mock_repo_class = MagicMock(return_value=mock_repo)
        monkeypatch.setattr(
            _subscription,
            "PalAccountSubscriptionRepository",
            mock_repo_class,
        )

        result = await _subscription.get_account_subscription_data_async(
            async_session,
            account_id,
            external_id,
        )

        assert result == subscription_data
        mock_repo_class.assert_called_once_with(async_session)
        mock_repo.get_by_account_and_external_id.assert_awaited_once_with(
            account_id,
            external_id,
        )


class TestGetCurrentSubscriptionDataAsync:
    """Current subscription lookup keeps polluted-account logging behavior."""

    @pytest.mark.asyncio
    async def test_returns_none_when_account_has_no_current_subscription(
        self,
        async_session: AsyncMock,
        account_id: uuid.UUID,
    ) -> None:
        account = MagicMock()
        account.id = account_id
        account.current_subscription_id = None

        result = await _subscription.get_current_subscription_data_async(
            async_session,
            account,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delegates_to_async_lookup(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        subscription_data: AccountSubscriptionData,
    ) -> None:
        account = MagicMock()
        account.id = account_id
        account.current_subscription_id = external_id
        mock_lookup = AsyncMock(return_value=subscription_data)
        monkeypatch.setattr(
            _subscription,
            "get_account_subscription_data_async",
            mock_lookup,
        )

        result = await _subscription.get_current_subscription_data_async(
            async_session,
            account,
        )

        assert result == subscription_data
        mock_lookup.assert_awaited_once_with(async_session, account_id, external_id)

    @pytest.mark.asyncio
    async def test_logs_when_current_subscription_is_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
    ) -> None:
        account = MagicMock()
        account.id = account_id
        account.current_subscription_id = external_id
        monkeypatch.setattr(
            _subscription,
            "get_account_subscription_data_async",
            AsyncMock(return_value=None),
        )
        mock_logger = MagicMock()
        monkeypatch.setattr(_subscription, "logger", mock_logger)

        result = await _subscription.get_current_subscription_data_async(
            async_session,
            account,
        )

        assert result is None
        mock_logger.error.assert_called_once()


class TestAddProjectToSubscriptionDataAsync:
    """Project subscription setup mirrors the sync Stripe setup path."""

    @pytest.mark.asyncio
    async def test_raises_when_subscription_plan_is_missing(
        self,
        async_session: AsyncMock,
        subscription_data: AccountSubscriptionData,
    ) -> None:
        with pytest.raises(ValueError, match="Subscription Plan not found"):
            await _subscription.add_project_to_subscription_data_async(
                async_session,
                subscription_data,
                MagicMock(),
                "test-account",
            )

    @pytest.mark.asyncio
    async def test_creates_prices_and_subscription_items(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        subscription_data: AccountSubscriptionData,
        subscription_plan_data: SubscriptionPlanData,
    ) -> None:
        project = MagicMock()
        project.id = uuid.uuid4()
        project.name = "test-project"
        project.display_name = "Test Project"
        project.account_id = uuid.uuid4()
        subscription = replace(
            subscription_data,
            subscription_plan=subscription_plan_data,
            stripe_subscription_id="sub_test",
        )
        initial_project_subscription = ProjectSubscriptionData(
            id=uuid.uuid4(),
            project_id=project.id,
            subscription_id=subscription.external_id,
            deleted=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        base_project_subscription = replace(
            initial_project_subscription,
            base_price_id="price_base",
        )
        call_project_subscription = replace(
            base_project_subscription,
            call_price_id="price_call",
        )
        order_project_subscription = replace(
            call_project_subscription,
            order_price_id="price_order",
        )

        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=None)
        mock_repo.get = AsyncMock(return_value=initial_project_subscription)
        mock_repo.update = AsyncMock(
            side_effect=[
                base_project_subscription,
                call_project_subscription,
                order_project_subscription,
            ]
        )
        monkeypatch.setattr(
            _subscription,
            "PalProjectSubscriptionRepository",
            MagicMock(return_value=mock_repo),
        )
        mock_stripe_product = MagicMock()
        mock_stripe_product.create_product_for_project.return_value = "prod_test"
        mock_stripe_product.create_billing_meter.side_effect = [
            "meter_call",
            "meter_order",
        ]
        mock_stripe_product.get_call_meter_event_name.return_value = "calls_event"
        mock_stripe_product.get_order_meter_event_name.return_value = "orders_event"
        mock_stripe_product.create_product_price.side_effect = [
            "price_base",
            "price_call",
            "price_order",
        ]
        monkeypatch.setattr(_subscription, "_stripe_product", mock_stripe_product)
        mock_stripe_subscription = MagicMock()
        monkeypatch.setattr(
            _subscription,
            "_stripe_subscription",
            mock_stripe_subscription,
        )

        result = await _subscription.add_project_to_subscription_data_async(
            async_session,
            subscription,
            project,
            "test-account",
        )

        assert result == order_project_subscription
        mock_repo.create.assert_awaited_once_with(
            project.id,
            subscription.external_id,
            stripe_product_id="prod_test",
        )
        mock_repo.get.assert_awaited_once_with(project.id, subscription.external_id)
        mock_repo.update.assert_any_await(
            initial_project_subscription.id,
            base_price_id="price_base",
        )
        mock_repo.update.assert_any_await(
            initial_project_subscription.id,
            call_price_id="price_call",
        )
        mock_repo.update.assert_any_await(
            initial_project_subscription.id,
            order_price_id="price_order",
        )
        mock_stripe_product.create_product_for_project.assert_called_once_with(
            project,
            "test-account",
            "Pro Plan",
        )
        mock_stripe_product.create_product_price.assert_any_call(
            "prod_test",
            nickname="Flat fee - Test Project",
            project=project,
            flat_fee=5000,
        )
        mock_stripe_product.create_product_price.assert_any_call(
            "prod_test",
            nickname="Calls - Test Project",
            project=project,
            meter_tiers=ANY,
            meter_id="meter_call",
        )
        mock_stripe_product.create_product_price.assert_any_call(
            "prod_test",
            nickname="Orders - Test Project",
            meter_tiers=ANY,
            project=project,
            meter_id="meter_order",
        )
        mock_stripe_subscription.add_subscription_item.assert_any_call(
            "sub_test",
            "price_base",
        )
        mock_stripe_subscription.add_subscription_item.assert_any_call(
            "sub_test",
            "price_call",
        )
        mock_stripe_subscription.add_subscription_item.assert_any_call(
            "sub_test",
            "price_order",
        )

    @pytest.mark.asyncio
    async def test_skips_base_and_order_prices_when_not_configured(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        subscription_data: AccountSubscriptionData,
        subscription_plan_data: SubscriptionPlanData,
    ) -> None:
        project = MagicMock()
        project.id = uuid.uuid4()
        project.name = "test-project"
        project.display_name = "Test Project"
        subscription = replace(
            subscription_data,
            subscription_plan=replace(
                subscription_plan_data,
                monthly_fee=0,
                order_overage_charge=0,
            ),
        )
        initial_project_subscription = ProjectSubscriptionData(
            id=uuid.uuid4(),
            project_id=project.id,
            subscription_id=subscription.external_id,
            deleted=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        call_project_subscription = replace(
            initial_project_subscription,
            call_price_id="price_call",
        )

        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=None)
        mock_repo.get = AsyncMock(return_value=initial_project_subscription)
        mock_repo.update = AsyncMock(return_value=call_project_subscription)
        monkeypatch.setattr(
            _subscription,
            "PalProjectSubscriptionRepository",
            MagicMock(return_value=mock_repo),
        )
        mock_stripe_product = MagicMock()
        mock_stripe_product.create_product_for_project.return_value = "prod_test"
        mock_stripe_product.create_billing_meter.return_value = "meter_call"
        mock_stripe_product.get_call_meter_event_name.return_value = "calls_event"
        mock_stripe_product.create_product_price.return_value = "price_call"
        monkeypatch.setattr(_subscription, "_stripe_product", mock_stripe_product)

        result = await _subscription.add_project_to_subscription_data_async(
            async_session,
            subscription,
            project,
            "test-account",
        )

        assert result == call_project_subscription
        mock_repo.update.assert_awaited_once_with(
            initial_project_subscription.id,
            call_price_id="price_call",
        )
        mock_stripe_product.create_billing_meter.assert_called_once()
        mock_stripe_product.create_product_price.assert_called_once_with(
            "prod_test",
            nickname="Calls - Test Project",
            project=project,
            meter_tiers=ANY,
            meter_id="meter_call",
        )

    @pytest.mark.asyncio
    async def test_raises_when_project_subscription_create_cannot_be_loaded(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        subscription_data: AccountSubscriptionData,
        subscription_plan_data: SubscriptionPlanData,
    ) -> None:
        project = MagicMock()
        project.id = uuid.uuid4()
        subscription = replace(
            subscription_data,
            subscription_plan=subscription_plan_data,
        )
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=None)
        mock_repo.get = AsyncMock(return_value=None)
        monkeypatch.setattr(
            _subscription,
            "PalProjectSubscriptionRepository",
            MagicMock(return_value=mock_repo),
        )
        mock_stripe_product = MagicMock()
        mock_stripe_product.create_product_for_project.return_value = "prod_test"
        monkeypatch.setattr(_subscription, "_stripe_product", mock_stripe_product)

        with pytest.raises(ValueError, match="Failed to create project subscription"):
            await _subscription.add_project_to_subscription_data_async(
                async_session,
                subscription,
                project,
                "test-account",
            )

    @pytest.mark.asyncio
    async def test_raises_when_call_price_update_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        subscription_data: AccountSubscriptionData,
        subscription_plan_data: SubscriptionPlanData,
    ) -> None:
        project = MagicMock()
        project.id = uuid.uuid4()
        project.name = "test-project"
        project.display_name = "Test Project"
        subscription = replace(
            subscription_data,
            subscription_plan=replace(subscription_plan_data, monthly_fee=0),
        )
        initial_project_subscription = ProjectSubscriptionData(
            id=uuid.uuid4(),
            project_id=project.id,
            subscription_id=subscription.external_id,
            deleted=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=None)
        mock_repo.get = AsyncMock(return_value=initial_project_subscription)
        mock_repo.update = AsyncMock(return_value=None)
        monkeypatch.setattr(
            _subscription,
            "PalProjectSubscriptionRepository",
            MagicMock(return_value=mock_repo),
        )
        mock_stripe_product = MagicMock()
        mock_stripe_product.create_product_for_project.return_value = "prod_test"
        mock_stripe_product.create_billing_meter.return_value = "meter_call"
        mock_stripe_product.get_call_meter_event_name.return_value = "calls_event"
        mock_stripe_product.create_product_price.return_value = "price_call"
        monkeypatch.setattr(_subscription, "_stripe_product", mock_stripe_product)

        with pytest.raises(ValueError, match="Failed to update call price"):
            await _subscription.add_project_to_subscription_data_async(
                async_session,
                subscription,
                project,
                "test-account",
            )


class TestCreateProjectSubscriptionDataAsync:
    """Project subscription creation uses pal repositories."""

    @pytest.mark.asyncio
    async def test_creates_with_pal_repository(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        subscription_data: AccountSubscriptionData,
    ) -> None:
        project = MagicMock()
        project.id = uuid.uuid4()
        project.account_id = account_id

        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=None)
        monkeypatch.setattr(
            _subscription,
            "PalProjectSubscriptionRepository",
            MagicMock(return_value=mock_repo),
        )
        mock_subscription_lookup = AsyncMock(return_value=subscription_data)
        monkeypatch.setattr(
            _subscription,
            "get_account_subscription_data_async",
            mock_subscription_lookup,
        )
        project_subscription_data = ProjectSubscriptionData(
            id=uuid.uuid4(),
            project_id=project.id,
            subscription_id=external_id,
            deleted=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        mock_add_project = AsyncMock(return_value=project_subscription_data)
        monkeypatch.setattr(
            _subscription,
            "add_project_to_subscription_data_async",
            mock_add_project,
        )

        result = await _subscription.create_project_subscription_data_async(
            async_session,
            project,
            external_id,
            "test-account",
        )

        assert result == project_subscription_data
        mock_subscription_lookup.assert_awaited_once_with(
            async_session,
            account_id,
            external_id,
        )
        mock_repo.get.assert_awaited_once_with(project.id, external_id)
        mock_add_project.assert_awaited_once_with(
            async_session,
            subscription_data,
            project,
            "test-account",
        )

    @pytest.mark.asyncio
    async def test_raises_when_subscription_is_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
    ) -> None:
        project = MagicMock()
        project.id = uuid.uuid4()
        project.account_id = account_id
        monkeypatch.setattr(
            _subscription,
            "PalProjectSubscriptionRepository",
            MagicMock(return_value=MagicMock()),
        )
        monkeypatch.setattr(
            _subscription,
            "get_account_subscription_data_async",
            AsyncMock(return_value=None),
        )

        with pytest.raises(
            ValueError, match=f"Subscription {external_id} does not exist"
        ):
            await _subscription.create_project_subscription_data_async(
                async_session,
                project,
                external_id,
                "test-account",
            )

    @pytest.mark.asyncio
    async def test_raises_when_project_subscription_exists(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        subscription_data: AccountSubscriptionData,
    ) -> None:
        project = MagicMock()
        project.id = uuid.uuid4()
        project.account_id = account_id
        existing_project_subscription = ProjectSubscriptionData(
            id=uuid.uuid4(),
            project_id=project.id,
            subscription_id=external_id,
            deleted=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=existing_project_subscription)
        monkeypatch.setattr(
            _subscription,
            "PalProjectSubscriptionRepository",
            MagicMock(return_value=mock_repo),
        )
        monkeypatch.setattr(
            _subscription,
            "get_account_subscription_data_async",
            AsyncMock(return_value=subscription_data),
        )

        with pytest.raises(ValueError, match="Project subscription already exists"):
            await _subscription.create_project_subscription_data_async(
                async_session,
                project,
                external_id,
                "test-account",
            )


class TestRemoveProjectSubscriptionDataAsync:
    """Project subscription removal uses pal repositories."""

    @pytest.mark.asyncio
    async def test_removes_project_subscription_and_stripe_items(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
        subscription_data: AccountSubscriptionData,
    ) -> None:
        project_id = uuid.uuid4()
        project_subscription_data = ProjectSubscriptionData(
            id=uuid.uuid4(),
            project_id=project_id,
            subscription_id=external_id,
            deleted=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            base_price_id="price_base",
            call_price_id="price_call",
            order_price_id="price_order",
        )
        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=project_subscription_data)
        mock_repo.soft_delete = AsyncMock(return_value=True)
        monkeypatch.setattr(
            _subscription,
            "PalProjectSubscriptionRepository",
            MagicMock(return_value=mock_repo),
        )
        mock_subscription_lookup = AsyncMock(
            return_value=replace(
                subscription_data,
                stripe_subscription_id="sub_test",
            )
        )
        monkeypatch.setattr(
            _subscription,
            "get_account_subscription_data_async",
            mock_subscription_lookup,
        )
        mock_stripe_subscription = MagicMock()
        monkeypatch.setattr(
            _subscription,
            "_stripe_subscription",
            mock_stripe_subscription,
        )

        await _subscription.remove_project_subscription_data_async(
            async_session,
            account_id,
            project_id,
            external_id,
        )

        mock_repo.get.assert_awaited_once_with(project_id, external_id)
        mock_subscription_lookup.assert_awaited_once_with(
            async_session,
            account_id,
            external_id,
        )
        mock_stripe_subscription.remove_subscription_item.assert_any_call(
            "sub_test",
            "price_base",
        )
        mock_stripe_subscription.remove_subscription_item.assert_any_call(
            "sub_test",
            "price_call",
        )
        mock_stripe_subscription.remove_subscription_item.assert_any_call(
            "sub_test",
            "price_order",
        )
        mock_repo.soft_delete.assert_awaited_once_with(project_id, external_id)

    @pytest.mark.asyncio
    async def test_returns_when_project_subscription_is_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
    ) -> None:
        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=None)
        mock_repo.soft_delete = AsyncMock()
        monkeypatch.setattr(
            _subscription,
            "PalProjectSubscriptionRepository",
            MagicMock(return_value=mock_repo),
        )
        mock_logger = MagicMock()
        monkeypatch.setattr(_subscription, "logger", mock_logger)

        await _subscription.remove_project_subscription_data_async(
            async_session,
            account_id,
            uuid.uuid4(),
            external_id,
        )

        mock_logger.debug.assert_called_once()
        mock_repo.soft_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_raises_when_subscription_is_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        async_session: AsyncMock,
        account_id: uuid.UUID,
        external_id: uuid.UUID,
    ) -> None:
        project_id = uuid.uuid4()
        project_subscription_data = ProjectSubscriptionData(
            id=uuid.uuid4(),
            project_id=project_id,
            subscription_id=external_id,
            deleted=False,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        mock_repo = MagicMock()
        mock_repo.get = AsyncMock(return_value=project_subscription_data)
        monkeypatch.setattr(
            _subscription,
            "PalProjectSubscriptionRepository",
            MagicMock(return_value=mock_repo),
        )
        monkeypatch.setattr(
            _subscription,
            "get_account_subscription_data_async",
            AsyncMock(return_value=None),
        )

        with pytest.raises(
            ValueError, match=f"Subscription {external_id} does not exist"
        ):
            await _subscription.remove_project_subscription_data_async(
                async_session,
                account_id,
                project_id,
                external_id,
            )
