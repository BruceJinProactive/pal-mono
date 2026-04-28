"""Tests for create_subscription_direct() in _stripe_subscription.py.

Validates that the Stripe subscription creation wrapper correctly builds
parameters, validates inputs, and handles Stripe API errors.
"""

from unittest.mock import MagicMock, patch

import pytest
import stripe

from services.subscription_service._stripe_subscription import (
    create_subscription_direct,
)


@pytest.fixture
def valid_line_items() -> list[dict]:
    return [
        {"price": "price_base_001", "quantity": 1},
        {"price": "price_call_001"},
        {"price": "price_order_001"},
    ]


@pytest.fixture
def valid_metadata() -> dict[str, str]:
    return {
        "subscription_external_id": "550e8400-e29b-41d4-a716-446655440000",
        "account_id": "660e8400-e29b-41d4-a716-446655440000",
    }


class TestCreateSubscriptionDirectValidation:
    """Input validation tests — no Stripe calls made."""

    def test_raises_if_customer_id_is_empty(
        self, valid_line_items: list[dict], valid_metadata: dict[str, str]
    ) -> None:
        with pytest.raises(ValueError, match="stripe_customer_id is required"):
            create_subscription_direct(
                stripe_customer_id="",
                line_items=valid_line_items,
                metadata=valid_metadata,
            )

    def test_raises_if_line_items_empty(self, valid_metadata: dict[str, str]) -> None:
        with pytest.raises(ValueError, match="line_items cannot be empty"):
            create_subscription_direct(
                stripe_customer_id="cus_test123",
                line_items=[],
                metadata=valid_metadata,
            )

    def test_raises_if_line_item_not_dict(self, valid_metadata: dict[str, str]) -> None:
        with pytest.raises(ValueError, match="Invalid line_item format"):
            create_subscription_direct(
                stripe_customer_id="cus_test123",
                line_items=["price_abc"],  # type: ignore[list-item]
                metadata=valid_metadata,
            )

    def test_raises_if_line_item_missing_price(
        self, valid_metadata: dict[str, str]
    ) -> None:
        with pytest.raises(ValueError, match="must have a 'price' key"):
            create_subscription_direct(
                stripe_customer_id="cus_test123",
                line_items=[{"quantity": 1}],
                metadata=valid_metadata,
            )

    def test_raises_if_days_until_due_less_than_1(
        self, valid_line_items: list[dict], valid_metadata: dict[str, str]
    ) -> None:
        with pytest.raises(ValueError, match="days_until_due must be at least 1"):
            create_subscription_direct(
                stripe_customer_id="cus_test123",
                line_items=valid_line_items,
                metadata=valid_metadata,
                days_until_due=0,
            )

    def test_raises_if_metadata_missing_subscription_external_id(
        self, valid_line_items: list[dict]
    ) -> None:
        with pytest.raises(
            ValueError, match="metadata must contain 'subscription_external_id'"
        ):
            create_subscription_direct(
                stripe_customer_id="cus_test123",
                line_items=valid_line_items,
                metadata={"account_id": "some-id"},
            )


class TestCreateSubscriptionDirectStripeCall:
    """Tests that verify correct Stripe API parameters."""

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_creates_subscription_with_send_invoice(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_sub = MagicMock()
        mock_sub.id = "sub_test123"
        mock_create.return_value = mock_sub

        result = create_subscription_direct(
            stripe_customer_id="cus_test123",
            line_items=valid_line_items,
            metadata=valid_metadata,
        )

        assert result.id == "sub_test123"
        mock_create.assert_called_once()

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["customer"] == "cus_test123"
        assert call_kwargs["collection_method"] == "send_invoice"
        assert call_kwargs["days_until_due"] == 30
        assert call_kwargs["metadata"] == valid_metadata
        assert call_kwargs["payment_settings"] == {
            "payment_method_types": ["card", "us_bank_account"],
        }

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_passes_line_items_with_quantity(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.return_value = MagicMock(id="sub_test123")

        create_subscription_direct(
            stripe_customer_id="cus_test123",
            line_items=valid_line_items,
            metadata=valid_metadata,
        )

        call_kwargs = mock_create.call_args[1]
        items = call_kwargs["items"]
        assert len(items) == 3
        assert items[0] == {"price": "price_base_001", "quantity": 1}
        assert items[1] == {"price": "price_call_001"}
        assert items[2] == {"price": "price_order_001"}

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_custom_days_until_due(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.return_value = MagicMock(id="sub_test123")

        create_subscription_direct(
            stripe_customer_id="cus_test123",
            line_items=valid_line_items,
            metadata=valid_metadata,
            days_until_due=45,
        )

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["days_until_due"] == 45

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_trial_end_passed_through(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.return_value = MagicMock(id="sub_test123")
        trial_ts = 1735689600  # 2025-01-01T00:00:00Z

        create_subscription_direct(
            stripe_customer_id="cus_test123",
            line_items=valid_line_items,
            metadata=valid_metadata,
            trial_end=trial_ts,
        )

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["trial_end"] == trial_ts

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_no_trial_end_when_not_provided(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.return_value = MagicMock(id="sub_test123")

        create_subscription_direct(
            stripe_customer_id="cus_test123",
            line_items=valid_line_items,
            metadata=valid_metadata,
        )

        call_kwargs = mock_create.call_args[1]
        assert "trial_end" not in call_kwargs

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_trial_end_zero_still_included(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.return_value = MagicMock(id="sub_test123")

        create_subscription_direct(
            stripe_customer_id="cus_test123",
            line_items=valid_line_items,
            metadata=valid_metadata,
            trial_end=0,
        )

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["trial_end"] == 0

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_idempotency_key_from_metadata(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.return_value = MagicMock(id="sub_test123")

        create_subscription_direct(
            stripe_customer_id="cus_test123",
            line_items=valid_line_items,
            metadata=valid_metadata,
        )

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["idempotency_key"] == "550e8400-e29b-41d4-a716-446655440000"

    @patch("services.subscription_service._stripe_subscription.validate_stripe_coupon")
    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_coupon_applied_when_valid(
        self,
        mock_create: MagicMock,
        mock_validate_coupon: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.return_value = MagicMock(id="sub_test123")
        mock_validate_coupon.return_value = None  # no error

        create_subscription_direct(
            stripe_customer_id="cus_test123",
            line_items=valid_line_items,
            metadata=valid_metadata,
            coupon_id="coupon_50off",
        )

        mock_validate_coupon.assert_called_once_with("coupon_50off")
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["coupon"] == "coupon_50off"

    @patch("services.subscription_service._stripe_subscription.validate_stripe_coupon")
    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_raises_when_coupon_validation_fails(
        self,
        mock_create: MagicMock,
        mock_validate_coupon: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_validate_coupon.side_effect = ValueError("Coupon not found")

        with pytest.raises(ValueError, match="Coupon not found"):
            create_subscription_direct(
                stripe_customer_id="cus_test123",
                line_items=valid_line_items,
                metadata=valid_metadata,
                coupon_id="bad_coupon",
            )

        mock_create.assert_not_called()

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_no_coupon_param_when_not_provided(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.return_value = MagicMock(id="sub_test123")

        create_subscription_direct(
            stripe_customer_id="cus_test123",
            line_items=valid_line_items,
            metadata=valid_metadata,
        )

        call_kwargs = mock_create.call_args[1]
        assert "coupon" not in call_kwargs


class TestCreateSubscriptionDirectErrors:
    """Tests for Stripe API error handling."""

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_raises_value_error_for_unknown_customer(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.side_effect = stripe.InvalidRequestError(
            message="No such customer: 'cus_gone'",
            param="customer",
        )

        with pytest.raises(ValueError, match=r"Stripe customer .* not found"):
            create_subscription_direct(
                stripe_customer_id="cus_gone",
                line_items=valid_line_items,
                metadata=valid_metadata,
            )

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_raises_value_error_for_invalid_price(
        self,
        mock_create: MagicMock,
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.side_effect = stripe.InvalidRequestError(
            message="No such price: 'price_bad'",
            param="items[0][price]",
        )

        with pytest.raises(ValueError, match="Invalid price ID"):
            create_subscription_direct(
                stripe_customer_id="cus_test123",
                line_items=[{"price": "price_bad"}],
                metadata=valid_metadata,
            )

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_reraises_other_invalid_request_errors(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.side_effect = stripe.InvalidRequestError(
            message="Something unexpected",
            param="unknown",
        )

        with pytest.raises(stripe.InvalidRequestError):
            create_subscription_direct(
                stripe_customer_id="cus_test123",
                line_items=valid_line_items,
                metadata=valid_metadata,
            )

    @patch(
        "services.subscription_service._stripe_subscription.stripe.Subscription.create"
    )
    def test_reraises_generic_stripe_error(
        self,
        mock_create: MagicMock,
        valid_line_items: list[dict],
        valid_metadata: dict[str, str],
    ) -> None:
        mock_create.side_effect = stripe.APIConnectionError(message="Network error")

        with pytest.raises(stripe.APIConnectionError):
            create_subscription_direct(
                stripe_customer_id="cus_test123",
                line_items=valid_line_items,
                metadata=valid_metadata,
            )
