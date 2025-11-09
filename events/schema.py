"""
Event definitions for AWS EventBridge.

All events must inherit from BaseEvent and define their structure and DetailType.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, ClassVar, Dict
from uuid import UUID


@dataclass
class BaseEvent:
    """
    Base class for all events.

    All events must inherit from this class and define:
    - detail_type: The EventBridge DetailType (class variable)
    - Event-specific fields as instance variables
    """

    # Subclasses must override this
    detail_type: ClassVar[str]

    def to_detail(self) -> Dict[str, Any]:
        """
        Convert the event to a dictionary for EventBridge detail.

        Handles UUID and datetime serialization automatically.
        Includes the detail_type in the output.
        """
        detail = {"detail_type": self.detail_type}
        for key, value in asdict(self).items():
            if isinstance(value, UUID):
                detail[key] = str(value)
            elif isinstance(value, datetime):
                detail[key] = value.isoformat()
            else:
                detail[key] = value
        return detail


@dataclass
class SampleEvent(BaseEvent):
    """Simple event for testing or sending basic messages to EventBridge."""

    detail_type: ClassVar[str] = "sample.Message"

    message: str
    timestamp: datetime


@dataclass
class CateringRequestCreated(BaseEvent):
    """Event published when a catering request is created."""

    detail_type: ClassVar[str] = "catering.RequestCreated"

    catering_request_id: UUID
    account_id: UUID
    event_date: datetime
    guest_count: int
    idempotency_key: str
    created_at: datetime


@dataclass
class CateringRequestUpdated(BaseEvent):
    """Event published when a catering request is updated."""

    detail_type: ClassVar[str] = "catering.RequestUpdated"

    catering_request_id: UUID
    account_id: UUID
    updated_fields: list[str]
    updated_at: datetime


@dataclass
class CateringRequestCancelled(BaseEvent):
    """Event published when a catering request is cancelled."""

    detail_type: ClassVar[str] = "catering.RequestCancelled"

    catering_request_id: UUID
    account_id: UUID
    cancellation_reason: str | None
    cancelled_at: datetime
