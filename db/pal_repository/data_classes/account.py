from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AccountData:
    """Immutable snapshot of an account.

    ORM objects never leave the repository layer — only this data object
    is returned to callers.
    """

    id: uuid.UUID
    name: str
    status: str
    onboarding_method: str
    contract_signed: bool
    created_at: datetime
    display_name: str | None = None
    icon_uri: str | None = None
    industry: str | None = None
    business_description: str | None = None
    business_faq: str | None = None
    business_promotions: str | None = None
    business_catalog: str | None = None
    business_others: str | None = None
    stripe_customer_id: str | None = None
    stripe_coupon_id: str | None = None
    current_subscription_id: uuid.UUID | None = None
    owner: str | None = None
    segment: str | None = None
    tier: str | None = None
    notes: str | None = None
    phone_number: str | None = None
    channels: tuple[str, ...] = field(default_factory=tuple)
    notification_preferences: dict[str, Any] = field(default_factory=dict)
    notification_email: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "notification_preferences", dict(self.notification_preferences)
        )
        if not isinstance(self.channels, tuple):
            object.__setattr__(self, "channels", tuple(self.channels))
