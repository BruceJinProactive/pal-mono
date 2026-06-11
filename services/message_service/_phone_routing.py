import json
import os

from api.schemas.chat.message import Broker
from utils.log import logger


def resolve_broker_from_sip_provider(sip_provider: str | None) -> Broker:
    try:
        return Broker(sip_provider) if sip_provider else Broker.TWILIO
    except ValueError:
        return Broker.TWILIO


def resolve_outbound_tn(sender_tn: str, broker: Broker) -> str:
    """Map internal routing TN to real outbound TN. Passthrough for non-PizzaCloud."""
    if broker != Broker.PIZZACLOUD:
        return sender_tn

    raw = os.environ.get("PIZZACLOUD_OUTBOUND_TN_MAP", "")
    if not raw:
        raise ValueError(
            f"PIZZACLOUD_OUTBOUND_TN_MAP env var is not set; "
            f"cannot resolve outbound TN for {sender_tn}"
        )

    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("PIZZACLOUD_OUTBOUND_TN_MAP is not valid JSON")

    if not isinstance(mapping, dict):
        raise ValueError("PIZZACLOUD_OUTBOUND_TN_MAP must be a JSON object")

    resolved = mapping.get(sender_tn)
    if resolved is None:
        raise ValueError(
            f"No outbound TN mapping found for {sender_tn} in "
            f"PIZZACLOUD_OUTBOUND_TN_MAP"
        )
    if not isinstance(resolved, str):
        raise ValueError(f"Outbound TN mapping value for {sender_tn} is not a string")

    logger.info(f"Outbound TN override: ***{sender_tn[-4:]} -> ***{resolved[-4:]}")
    return resolved
