import json
import uuid
from dataclasses import dataclass
from typing import Optional

import stripe

import db
from utils.log import logger

DEFAULT_CURRENCY = "usd"
CALLS_METER_EVENT_NAME = "pal_calls"
ORDERS_METER_EVENT_NAME = "pal_orders"


@dataclass
class MeterTier:
    last_unit: int | None  # ending quantity (inclusive)
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


def find_existing_meter(event_name: str) -> Optional[str]:
    """
    Search for an existing billing meter by event_name.
    """
    try:
        # Fetch all meters and filter by event_name, handling pagination
        starting_after = None
        while True:
            if starting_after:
                existing_meters = stripe.billing.Meter.list(
                    limit=100, starting_after=starting_after
                )
            else:
                existing_meters = stripe.billing.Meter.list(limit=100)

            # Check current page for matching meter
            for existing_meter in existing_meters.data:
                if existing_meter.event_name == event_name:
                    logger.info(f"Found existing meter with ID: {existing_meter.id}")
                    return existing_meter.id

            # Check if there are more pages
            if not existing_meters.has_more:
                break

            # Get the last meter ID for the next page
            starting_after = existing_meters.data[-1].id
        logger.info("No existing meter found")
        return None
    except Exception as err:
        logger.error(f"Failed to search for existing meter: {err}")
        return None


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
    except stripe.InvalidRequestError as err:
        if "An active meter already exists" in str(err):
            logger.info("Meter already exists, searching for existing one to reuse.")
        else:
            logger.warning(f"Unknown error, will try to fetch existing: {err}")
        # try to find and use existing meter
        existing_meter_id = find_existing_meter(event_name)
        if existing_meter_id:
            logger.info(f"Found existing meter: {existing_meter_id}")
            return existing_meter_id
        # otherwise raise the error to prevent silent failure
        raise err
    except Exception as err:
        logger.error(
            f"Failed to create billing meter: {err}",
            extra={"event_name": event_name, "display_name": display_name},
        )
        raise err


def create_product_price(
    product_id: str,
    nickname: str,
    project: db.Project,
    flat_fee: int | None = None,
    meter_tiers: list[MeterTier] | None = None,
    meter_id: str | None = None,
):
    if flat_fee is not None and meter_tiers is not None:
        raise ValueError("Flat fee and meter tiers cannot be both set!")
    if meter_tiers is not None and meter_id is None:
        raise ValueError("meter_id is required when meter_tiers are provided")
    params = {
        "product": product_id,
        "currency": DEFAULT_CURRENCY,
        "metadata": {
            "project_name": project.name,
        },
        "nickname": nickname,
        "recurring": {
            "interval": "month",
        },
    }
    if flat_fee is not None:
        params["unit_amount"] = flat_fee
    if meter_tiers:
        params["tiers"] = [
            {
                "up_to": t.last_unit or "inf",
                "unit_amount": t.per_unit or 0,
            }
            for t in meter_tiers
        ]
        params["billing_scheme"] = "tiered"
        params["tiers_mode"] = "graduated"
        params["recurring"]["usage_type"] = "metered"
        params["recurring"]["meter"] = meter_id

    try:
        price = stripe.Price.create(**params)
        return price.id
    except Exception as err:
        logger.error(
            f"Failed to create stripe price: {err}",
            extra={"params": json.dumps(params)},
        )
        raise err
