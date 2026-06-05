import sys
import uuid
from datetime import UTC, datetime
from importlib import import_module
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

sys.modules.setdefault("services.agent_service", ModuleType("services.agent_service"))

SubscriptionStatus: Any = import_module("db.tables.types").SubscriptionStatus
create_stripe_checkout_url: Any = import_module(
    "services.subscription_service._subscription"
).create_stripe_checkout_url


def _make_subscription(account_id: uuid.UUID, external_id: uuid.UUID) -> MagicMock:
    subscription = MagicMock()
    subscription.account_id = account_id
    subscription.external_id = external_id
    subscription.status = SubscriptionStatus.pending
    subscription.stripe_subscription_id = None
    subscription.start_date = datetime.now(UTC)
    return subscription


def _make_project_subscription(
    project_id: uuid.UUID,
    base_price_id: str,
    call_price_id: str,
) -> MagicMock:
    project_subscription = MagicMock()
    project_subscription.id = uuid.uuid4()
    project_subscription.project_id = project_id
    project_subscription.base_price_id = base_price_id
    project_subscription.call_price_id = call_price_id
    project_subscription.order_price_id = None
    return project_subscription


def _make_account() -> MagicMock:
    account = MagicMock()
    account.stripe_customer_id = None
    account.stripe_coupon_id = None
    return account


def _make_project(project_id: uuid.UUID) -> MagicMock:
    project = MagicMock()
    project.id = project_id
    project.name = f"project-{project_id.hex[:8]}"
    project.display_name = "Selected Location"
    return project


@patch("services.subscription_service._subscription._stripe_subscription")
@patch("services.subscription_service._subscription.account_service")
@patch("services.subscription_service._subscription.project_service")
@patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
@patch(
    "services.subscription_service._subscription.get_account_subscription_by_external_id"
)
def test_create_stripe_checkout_url_includes_only_selected_project_prices(
    mock_get_subscription: MagicMock,
    mock_project_subscription_repository: MagicMock,
    mock_project_service: MagicMock,
    mock_account_service: MagicMock,
    mock_stripe_subscription: MagicMock,
) -> None:
    session = MagicMock()
    account_id = uuid.uuid4()
    external_id = uuid.uuid4()
    selected_project_id = uuid.uuid4()
    other_project_id = uuid.uuid4()
    subscription = _make_subscription(account_id, external_id)
    selected_project_subscription = _make_project_subscription(
        selected_project_id,
        "price_base_selected",
        "price_call_selected",
    )
    other_project_subscription = _make_project_subscription(
        other_project_id,
        "price_base_other",
        "price_call_other",
    )
    checkout_session = MagicMock()
    checkout_session.url = "https://checkout.stripe.com/selected"

    mock_get_subscription.return_value = subscription
    mock_project_subscription_repository.return_value.get_project_subscriptions_by_subscription_id.return_value = [
        selected_project_subscription,
        other_project_subscription,
    ]
    mock_project_service.get_project.return_value = _make_project(selected_project_id)
    mock_account_service.get_account_by_id.return_value = _make_account()
    mock_stripe_subscription.create_checkout_session.return_value = checkout_session

    result = create_stripe_checkout_url(
        session=session,
        account_id=account_id,
        external_id=external_id,
        customer_email=None,
        redirect_url_prefix="https://admin.example.com/billing",
        project_ids=[selected_project_id],
    )

    assert result == "https://checkout.stripe.com/selected"
    mock_project_service.get_project.assert_called_once_with(
        session, selected_project_id
    )
    mock_stripe_subscription.create_checkout_session.assert_called_once()
    line_items = mock_stripe_subscription.create_checkout_session.call_args.kwargs[
        "line_items"
    ]
    assert line_items == [
        {"price": "price_base_selected", "quantity": 1},
        {"price": "price_call_selected"},
    ]


@patch("services.subscription_service._subscription._stripe_subscription")
@patch("services.subscription_service._subscription.account_service")
@patch("services.subscription_service._subscription.project_service")
@patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
@patch(
    "services.subscription_service._subscription.get_account_subscription_by_external_id"
)
def test_create_stripe_checkout_url_includes_all_project_prices_when_project_ids_omitted(
    mock_get_subscription: MagicMock,
    mock_project_subscription_repository: MagicMock,
    mock_project_service: MagicMock,
    mock_account_service: MagicMock,
    mock_stripe_subscription: MagicMock,
) -> None:
    session = MagicMock()
    account_id = uuid.uuid4()
    external_id = uuid.uuid4()
    first_project_id = uuid.uuid4()
    second_project_id = uuid.uuid4()
    subscription = _make_subscription(account_id, external_id)
    checkout_session = MagicMock()
    checkout_session.url = "https://checkout.stripe.com/all"

    mock_get_subscription.return_value = subscription
    mock_project_subscription_repository.return_value.get_project_subscriptions_by_subscription_id.return_value = [
        _make_project_subscription(
            first_project_id,
            "price_base_first",
            "price_call_first",
        ),
        _make_project_subscription(
            second_project_id,
            "price_base_second",
            "price_call_second",
        ),
    ]
    mock_project_service.get_project.side_effect = [
        _make_project(first_project_id),
        _make_project(second_project_id),
    ]
    mock_account_service.get_account_by_id.return_value = _make_account()
    mock_stripe_subscription.create_checkout_session.return_value = checkout_session

    result = create_stripe_checkout_url(
        session=session,
        account_id=account_id,
        external_id=external_id,
        customer_email=None,
        redirect_url_prefix="https://admin.example.com/billing",
    )

    assert result == "https://checkout.stripe.com/all"
    assert mock_project_service.get_project.call_args_list == [
        call(session, first_project_id),
        call(session, second_project_id),
    ]
    line_items = mock_stripe_subscription.create_checkout_session.call_args.kwargs[
        "line_items"
    ]
    assert line_items == [
        {"price": "price_base_first", "quantity": 1},
        {"price": "price_call_first"},
        {"price": "price_base_second", "quantity": 1},
        {"price": "price_call_second"},
    ]


@patch("services.subscription_service._subscription._stripe_subscription")
@patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
@patch(
    "services.subscription_service._subscription.get_account_subscription_by_external_id"
)
def test_create_stripe_checkout_url_rejects_unknown_selected_project(
    mock_get_subscription: MagicMock,
    mock_project_subscription_repository: MagicMock,
    mock_stripe_subscription: MagicMock,
) -> None:
    session = MagicMock()
    account_id = uuid.uuid4()
    external_id = uuid.uuid4()
    selected_project_id = uuid.uuid4()
    missing_project_id = uuid.uuid4()

    mock_get_subscription.return_value = _make_subscription(account_id, external_id)
    mock_project_subscription_repository.return_value.get_project_subscriptions_by_subscription_id.return_value = [
        _make_project_subscription(
            selected_project_id,
            "price_base_selected",
            "price_call_selected",
        )
    ]

    with pytest.raises(ValueError, match="not included in this subscription"):
        create_stripe_checkout_url(
            session=session,
            account_id=account_id,
            external_id=external_id,
            customer_email=None,
            redirect_url_prefix="https://admin.example.com/billing",
            project_ids=[missing_project_id],
        )

    mock_stripe_subscription.create_checkout_session.assert_not_called()


@patch("services.subscription_service._subscription._stripe_subscription")
@patch("services.subscription_service._subscription.ProjectSubscriptionRepository")
@patch(
    "services.subscription_service._subscription.get_account_subscription_by_external_id"
)
def test_create_stripe_checkout_url_rejects_empty_selected_project_list(
    mock_get_subscription: MagicMock,
    mock_project_subscription_repository: MagicMock,
    mock_stripe_subscription: MagicMock,
) -> None:
    session = MagicMock()
    account_id = uuid.uuid4()
    external_id = uuid.uuid4()
    selected_project_id = uuid.uuid4()

    mock_get_subscription.return_value = _make_subscription(account_id, external_id)
    mock_project_subscription_repository.return_value.get_project_subscriptions_by_subscription_id.return_value = [
        _make_project_subscription(
            selected_project_id,
            "price_base_selected",
            "price_call_selected",
        )
    ]

    with pytest.raises(ValueError, match="At least one project_id"):
        create_stripe_checkout_url(
            session=session,
            account_id=account_id,
            external_id=external_id,
            customer_email=None,
            redirect_url_prefix="https://admin.example.com/billing",
            project_ids=[],
        )

    mock_stripe_subscription.create_checkout_session.assert_not_called()
