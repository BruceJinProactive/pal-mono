from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class YelpApiResponse(BaseModel):
    """Class to handle Yelp API response data"""

    status: int
    reason: str
    decoded_body: dict


class YelpAccessToken(BaseModel):
    """
    This class represents an access token for Yelp API authentication.
    It can be used for both simple API key tokens and OAuth access tokens.
    """

    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

    def is_expired(self) -> bool:
        """
        Checks if the token is expired.

        Returns:
            bool: True if the token is expired, False otherwise
        """
        if self.expires_in is None:
            return False  # API keys don't expire

        expiration_time = self.created_at + timedelta(seconds=self.expires_in)
        return datetime.now() > expiration_time

    def get_token_header_value(self) -> str:
        """Returns the properly formatted token for use in headers"""
        return f"{self.token_type} {self.access_token}"

    def is_valid(self) -> bool:
        """Basic check to see if token has required fields and is not expired"""
        return bool(self.access_token and self.token_type and not self.is_expired())


######### YELP BOOKINGS API CLASSES (CREDIT CARD NOT REQUIRED) ############


class ReservationTime(BaseModel):
    """Individual reservation time slot"""

    credit_card_required: bool = Field(
        description="Whether a credit card is required for this time slot"
    )
    time: str = Field(
        description="Available time slot in HH:MM format", pattern=r"^\d{2}:\d{2}$"
    )


class DailyReservationTimes(BaseModel):
    """Reservation times for a specific date"""

    date: str = Field(
        description="Date for these reservation times in YYYY-mm-dd format",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    times: List[ReservationTime] = Field(
        description="List of available time slots for this date"
    )


class CoversRange(BaseModel):
    """Range of party sizes supported by the restaurant"""

    min_party_size: int = Field(
        description="Minimum party size the restaurant can accommodate", gt=0
    )
    max_party_size: int = Field(
        description="Maximum party size the restaurant can accommodate", gt=0
    )


class YelpBookingsOpeningsResponseCreditCardNotRequired(BaseModel):
    """Response from Yelp Bookings openings endpoint"""

    reservation_times: List[DailyReservationTimes] = Field(
        description="Available reservation times across multiple days (typically 4 days: day before, current day, and 2 days after requested date)"
    )
    covers_range: Optional[CoversRange] = Field(
        default=None,
        description="Range of party sizes supported (included when get_covers_range=true)",
    )


class YelpBookingsHoldsResponseCreditCardNotRequired(BaseModel):
    """Response from Yelp Bookings holds endpoint"""

    cancellation_policy: str = Field(
        description="The restaurant's cancellation policy text"
    )
    credit_card_hold: bool = Field(
        description="Whether a credit card hold is required for this reservation"
    )
    expires_at: float = Field(
        description="Unix timestamp when the hold expires (holds are valid for 5 minutes)"
    )
    hold_id: str = Field(
        description="Unique identifier for this hold, required to place the actual reservation"
    )
    is_editable: bool = Field(
        description="Whether the reservation can be edited after being placed"
    )
    last_cancellation_date: float = Field(
        description="Unix timestamp of the last date/time the reservation can be cancelled"
    )
    notes: str = Field(description="Additional notes from the restaurant")
    reserve_url: str = Field(
        description="URL to complete the reservation on Yelp's platform"
    )


class YelpBookingsReservationsResponseCreditCardNotRequired(BaseModel):
    """Response from Yelp Bookings reservations endpoint"""

    confirmation_url: str = Field(
        description="URL to view the confirmed reservation on Yelp's platform"
    )
    notes: str = Field(description="Additional notes for the reservation")
    reservation_id: str = Field(
        description="Unique identifier for the confirmed reservation"
    )


######### YELP WAITLIST API CLASSES ############


class WaitlistState(str, Enum):
    """Possible states for the waitlist"""

    OPEN = "OPEN"
    ON_MY_WAY = "ON_MY_WAY"
    CLOSED = "CLOSED"


class WaitlistClosedReason(str, Enum):
    """Possible reasons why the waitlist is closed"""

    RESTO_CLOSED = "resto_closed"
    WAITLIST_CLOSED = "waitlist_closed"
    NO_CURRENT_WAIT = "no_current_wait"
    SPECIAL_EVENT = "special_event"
    REMOTE_ENTRY_DISABLED = "remote_entry_disabled"

    def get_description(self) -> str:
        """Get human-readable description for the closed reason"""
        descriptions = {
            "resto_closed": "The restaurant is out of the business hour",
            "waitlist_closed": "The waitlist is closed for the restaurant",
            "no_current_wait": "There is currently no wait for the restaurant",
            "special_event": "The restaurant is closed for a special event",
            "remote_entry_disabled": "Remote entry feature is disabled for the restaurant",
        }
        return descriptions.get(self.value, "Description not available")


class WaitEstimate(BaseModel):
    """Wait time estimates for a specific party size range"""

    est_wait: int = Field(description="Estimated wait time in minutes", ge=0)
    min_wait: int = Field(description="Minimum wait time in minutes", ge=0)
    wait_range: str = Field(description="Wait range as a string representation")
    max_wait: Optional[int] = Field(
        default=None,
        description="Maximum wait time in minutes (not present for 7+ party size)",
        ge=0,
    )


class YelpWaitlistStatusResponse(BaseModel):
    """Response from Yelp Waitlist Status endpoint"""

    business_id: str = Field(description="Yelp business identifier")
    state: WaitlistState = Field(description="Current state of the waitlist")
    closed_reason: Optional[WaitlistClosedReason] = Field(
        default=None,
        description="Reason why the waitlist is closed, if applicable (only present when state is CLOSED)",
    )
    wait_estimates: dict[str, WaitEstimate] = Field(
        description="Wait time estimates for different party size ranges (e.g., '1-2', '3-4', '5-6', '7+')"
    )


class YelpWaitlistJoinQueueResponse(BaseModel):
    """Response from Yelp Waitlist Join Queue endpoint"""

    visit_id: str = Field(description="Encrypted visit identifier")
    queue_time: int = Field(
        description="Unix timestamp (seconds) when the visit was enqueued"
    )
    party_size: int = Field(description="The number of guests in the visit", gt=0)
    arrive_by_time: int = Field(
        description="Unix timestamp (seconds) when guest should be told to arrive at restaurant"
    )
    expected_seating_time_min: int = Field(
        description="Unix timestamp (seconds) lower bound of estimated seating time"
    )
    expected_seating_time_max: int = Field(
        description="Unix timestamp (seconds) upper bound of estimated seating time"
    )
