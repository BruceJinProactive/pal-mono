from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(
    frozen=True
)  # frozen=True makes instances immutable (raises AttributeError on assignment)
class ProjectData:
    """Immutable snapshot of a project.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    name: str
    account_id: uuid.UUID
    agent_id: uuid.UUID
    created_at: datetime
    display_name: str | None = None
    raw_config: dict[str, object] = field(default_factory=dict)
    channel_identifiers: list[str] = field(default_factory=list)
    store_hours: str | None = None
    address: str | None = None
    product_info: str | None = None
    service_instruction: str | None = None
    order_integration_id: uuid.UUID | None = None
    timezone: str | None = None
    transfer_message: str | None = None
    transfer_phone_number: str | None = None
    show_agent_caller_id: bool | None = None
    reservation_link: str | None = None
    ordering_link: str | None = None
    call_forwarding_setup_completed: bool | None = None
    stripe_customer_id: str | None = None
    stripe_coupon_id: str | None = None
    current_subscription_id: uuid.UUID | None = None
    google_place_id: str | None = None
    business_hours: dict[str, object] | None = None
    business_hours_last_updated: datetime | None = None
    updated_at: datetime | None = None
