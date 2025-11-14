import uuid
from dataclasses import dataclass


@dataclass
class ProjectParams:
    name: str | None = None
    display_name: str | None = None
    agent_id: uuid.UUID | None = None
    raw_config: dict | None = None
    channel_identifiers: list[str] | None = None
    store_hours: str | None = None
    address: str | None = None
    product_info: str | None = None
    service_instruction: str | None = None
    order_integration_id: uuid.UUID | None = None
    timezone: str | None = None
    transfer_message: str | None = None
    transfer_phone_number: str | None = None
    reservation_link: str | None = None
    ordering_link: str | None = None
    google_place_id: str | None = None
