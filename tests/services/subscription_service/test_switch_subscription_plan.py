import sys
import uuid
from datetime import UTC, datetime
from importlib import import_module
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from db.tables.subscriptions import SubscriptionStatus

sys.modules.setdefault("services.agent_service", ModuleType("services.agent_service"))

_subscription: Any = import_module("services.subscription_service._subscription")


def _plan(name: str, active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        name=name,
        active=active,
        monthly_fee=1000,
        call_quota=100,
        call_overage_charge=25,
        order_quota=10,
        order_overage_charge=50,
    )


def test_switch_subscription_plan_allows_current_inactive_plan() -> None:
    old_plan = _plan("Retired Growth", active=False)
    new_plan = _plan("Essentials", active=True)
    account_id = uuid.uuid4()
    subscription_external_id = uuid.uuid4()
    current_subscription = SimpleNamespace(
        external_id=subscription_external_id,
        subscription_plan_id=old_plan.id,
        status=SubscriptionStatus.active,
        stripe_subscription_id=None,
    )
    account = MagicMock()
    account.id = account_id
    account.name = "test-account"
    account.current_subscription_id = subscription_external_id
    context = MagicMock()
    context.email = "admin@test.com"
    updated_subscription = SimpleNamespace(
        external_id=subscription_external_id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=None,
    )
    plan_repo = MagicMock()
    plan_repo.get_subscription_plan_by_id_including_inactive.return_value = old_plan
    plan_repo.get_subscription_plan_by_id.return_value = new_plan
    project_subscription_repo = MagicMock()
    project_subscription_repo.get_project_subscriptions_by_subscription_id.return_value = [
        SimpleNamespace(id=uuid.uuid4())
    ]

    with (
        patch.object(
            _subscription,
            "get_current_subscription",
            return_value=current_subscription,
        ),
        patch.object(
            _subscription,
            "SubscriptionPlanRepository",
            return_value=plan_repo,
        ),
        patch.object(
            _subscription,
            "ProjectSubscriptionRepository",
            return_value=project_subscription_repo,
        ),
        patch.object(
            _subscription,
            "update_account_subscription",
            return_value=updated_subscription,
        ) as update_account_subscription,
    ):
        new_subscription, old_plan_name, new_plan_name = (
            _subscription.switch_subscription_plan(
                session=MagicMock(),
                context=context,
                account=account,
                new_plan_id=new_plan.id,
            )
        )

    assert new_subscription == updated_subscription
    assert old_plan_name == old_plan.name
    assert new_plan_name == new_plan.name
    plan_repo.get_subscription_plan_by_id_including_inactive.assert_called_once_with(
        old_plan.id
    )
    plan_repo.get_subscription_plan_by_id.assert_called_once_with(new_plan.id)
    update_account_subscription.assert_called_once()


def test_switch_project_subscription_plan_allows_current_inactive_plan() -> None:
    old_plan = _plan("Retired Growth", active=False)
    new_plan = _plan("Essentials", active=True)
    project_id = uuid.uuid4()
    project_external_id = uuid.uuid4()
    active_project_subscription = SimpleNamespace(
        id=uuid.uuid4(),
        external_id=project_external_id,
        subscription_id=project_external_id,
        subscription_plan_id=old_plan.id,
        status=SubscriptionStatus.active,
        stripe_subscription_id="sub_test",
    )
    project = SimpleNamespace(
        id=project_id,
        account_id=uuid.uuid4(),
        name="test-project",
        display_name="Test Project",
    )
    account = SimpleNamespace(id=project.account_id, name="test-account")
    context = MagicMock()
    context.email = "admin@test.com"
    updated_subscription = SimpleNamespace(
        external_id=project_external_id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=None,
    )
    plan_repo = MagicMock()
    plan_repo.get_subscription_plan_by_id_including_inactive.return_value = old_plan
    plan_repo.get_subscription_plan_by_id.return_value = new_plan
    project_subscription_repo = MagicMock()
    project_subscription_repo.get_active_project_subscription.return_value = (
        active_project_subscription
    )

    with (
        patch.object(
            _subscription,
            "ProjectSubscriptionRepository",
            return_value=project_subscription_repo,
        ),
        patch.object(
            _subscription,
            "SubscriptionPlanRepository",
            return_value=plan_repo,
        ),
        patch.object(
            _subscription.project_service,
            "get_project",
            return_value=project,
        ),
        patch.object(
            _subscription.account_service,
            "get_account_by_id",
            return_value=account,
        ),
        patch.object(
            _subscription,
            "_update_stripe_subscription_for_project_plan_switch",
        ) as update_stripe_subscription,
        patch.object(
            _subscription,
            "update_project_subscription",
            return_value=updated_subscription,
        ) as update_project_subscription,
    ):
        new_subscription, old_plan_name, new_plan_name = (
            _subscription.switch_project_subscription_plan(
                session=MagicMock(),
                context=context,
                project_id=project_id,
                new_plan_id=new_plan.id,
            )
        )

    assert new_subscription == updated_subscription
    assert old_plan_name == old_plan.name
    assert new_plan_name == new_plan.name
    plan_repo.get_subscription_plan_by_id_including_inactive.assert_called_once_with(
        old_plan.id
    )
    plan_repo.get_subscription_plan_by_id.assert_called_once_with(new_plan.id)
    update_stripe_subscription.assert_called_once()
    update_project_subscription.assert_called_once()
