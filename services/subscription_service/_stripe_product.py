import json
import uuid
from dataclasses import dataclass

import stripe

import db
from utils.log import logger

DEFAULT_CURRENCY = "usd"
CALLS_METER_EVENT_NAME = "pal_calls"
ORDERS_METER_EVENT_NAME = "pal_orders"


@dataclass
class MeterTier:
    last_unit: int | None  # ending quantity (inclusive)
    flat_fee: int | None  # flat fee in cents
    per_unit: int | None  # per unit charge in cents


def create_product(account_name, plan_name: str):
    try:
        product = stripe.Product.create(
            name=f"{plan_name} - {account_name}",
            description="Monthly subscription plan",
            metadata={"account_name": account_name, "type": "usage_billing"},
        )
        return product.id

    except stripe.StripeError as e:
        logger.error(
            f"Failed to create Stripe product for account {account_name}: {e}",
            extra={"account_name": account_name},
        )
        raise


def get_call_meter_event_name(project_id: uuid.UUID) -> str:
    return f"calls_{str(project_id)}"


def get_order_meter_event_name(project_id: uuid.UUID) -> str:
    return f"orders_{str(project_id)}"


def create_billing_meter(display_name, event_name: str) -> str:
    try:
        meter = stripe.billing.Meter.create(
            display_name=display_name,
            event_name=event_name,
            default_aggregation={"formula": "count"},
            customer_mapping={
                "type": "by_id",
                "event_payload_key": "stripe_customer_id",
            },
        )
        return meter.id
    except Exception as err:
        logger.error(
            f"Failed to create billing meter: {err}",
            extra={"event_name": event_name, "display_name": display_name},
        )
        raise err


def create_product_price(
    product_id: str,
    meter_id: str,
    nickname: str,
    meter_tiers: list[MeterTier],
    project: db.Project,
):
    params = {
        "product": product_id,
        "currency": DEFAULT_CURRENCY,
        "metadata": {
            "project_name": project.name,
            "meter_id": meter_id,
        },
        "nickname": nickname,
        "recurring": {
            "interval": "month",
            "usage_type": "metered",
            "meter": meter_id,
        },
        "billing_scheme": "tiered",
        "tiers_mode": "graduated",
        "tiers": [
            {
                "up_to": t.last_unit or "inf",
                "unit_amount": t.per_unit or 0,
                "flat_amount": t.flat_fee or 0,
            }
            for t in meter_tiers
        ],
    }
    try:
        price = stripe.Price.create(**params)
        return price.id
    except Exception as err:
        logger.error(
            f"Failed to create stripe price: {err}",
            extra={"params": json.dumps(params)},
        )
        raise err
