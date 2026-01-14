import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

from db.tables.types import IntegrationProvider


@dataclass
class ReservationData:
    """
    Standardized reservation/waitlist data structure for all tools.

    This class provides a common interface for reservation and waitlist data
    across all integration providers (Yelp, MiniTable, Resy, OpenTable, etc.).

    Entry Types:
        - "reservation": Future booking (has reservation_time)
        - "waitlist": Immediate queue entry (has arrive_by_time, expected_seating_time)
    """

    # Required fields
    conversation_id: uuid.UUID
    vendor: IntegrationProvider

    # Entry type discriminator
    entry_type: Literal["reservation", "waitlist"] = "reservation"

    # External system identifiers
    reservation_id: Optional[str] = None  # visit_id, waitlist_id, etc.
    store_id: Optional[str] = None
    tracking_link: Optional[str] = None  # URL to manage/view entry

    # Status from external system
    status: Optional[str] = None  # "queued", "confirmed", "seated", etc.

    # Reservation details
    table_size: Optional[int] = None
    special_requests: Optional[str] = None

    # Timestamps
    reservation_time: Optional[datetime] = None  # When reservation is scheduled for

    # Waitlist-specific fields (from Yelp, etc.)
    arrive_by_time: Optional[datetime] = None  # When customer should arrive
    expected_seating_time: Optional[datetime] = None  # Estimated seating time

    def __post_init__(self):
        """Validate required fields."""
        if not self.conversation_id:
            raise ValueError("conversation_id is required")

        if not isinstance(self.conversation_id, uuid.UUID):
            raise TypeError(
                f"conversation_id must be a uuid.UUID, got {type(self.conversation_id).__name__}"
            )

        if self.entry_type not in ("reservation", "waitlist"):
            raise ValueError("entry_type must be 'reservation' or 'waitlist'")
