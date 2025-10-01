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


######### YELP CREDIT CARD REQUIRED API CLASSES ############


class YelpBookingsOpeningsSlotCreditCardRequired(BaseModel):
    """Individual availability slot from open API endpoint"""

    timestamp: int = Field(description="Unix timestamp for the availability slot")
    formatted_time: str = Field(
        description="Human-readable time format (e.g., '3:45 PM')"
    )
    form_action: str = Field(description="Form action URL for making reservation")
    csrf_token: str = Field(description="CSRF token for the reservation form")
    isodate: str = Field(description="ISO date string with timezone")


class YelpBookingsOpeningsGroupCreditCardRequired(BaseModel):
    """Availability group for a specific date/time search"""

    availability_list: List[YelpBookingsOpeningsSlotCreditCardRequired] = Field(
        description="List of available time slots"
    )
    date: str = Field(description="Date in human-readable format (e.g., 'Thu, Jul 10')")
    covers: int = Field(description="Number of people for the search")
    time: str = Field(description="Requested time (e.g., '6:00 PM')")
    timestamp: int = Field(description="Unix timestamp for the requested time")
    msg: str = Field(description="Message template for availability")
    isodate: str = Field(description="ISO date string for requested time")


class YelpBookingsOpeningsRequestCreditCardRequired(BaseModel):
    """Request parameters for open API availability endpoint"""

    covers: int = Field(
        description="How many people are attending the reservation (min. value is 1; max value is 10).",
        ge=1,
        le=10,
    )
    date: str = Field(
        description="The date for the reservation, format is YYYY-mm-dd",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    time: str = Field(
        description="The time of the requested reservation, format is HH:MM:SS",
        pattern=r"^\d{2}:\d{2}:\d{2}$",
    )
    days_before: str = Field(default="0", description="Days before to search")
    days_after: str = Field(default="0", description="Days after to search")
    biz_id: str = Field(description="Business ID")
    biz_lat: str = Field(description="Business latitude")
    biz_long: str = Field(description="Business longitude")
    num_results_after: Optional[int] = Field(
        default=None,
        description="Set to 0 if user wants to know the openings before the current result, otherwise don't include this field",
    )
    num_results_before: Optional[int] = Field(
        default=None,
        description="Set to 0 if user wants to know the openings after the current result, otherwise don't include this field",
    )


class YelpBookingsOpeningsResponseCreditCardRequired(BaseModel):
    """Response from open API availability endpoint"""

    success: bool = Field(description="Whether the request was successful")
    availability_data: List[YelpBookingsOpeningsGroupCreditCardRequired] = Field(
        description="Available reservation times grouped by search criteria"
    )
    availability_profile: str = Field(
        description="Availability profile (e.g., 'medium')"
    )
    exact_match: Optional[YelpBookingsOpeningsSlotCreditCardRequired] = Field(
        default=None, description="Exact match for requested time, if available"
    )
    closest_match: Optional[YelpBookingsOpeningsSlotCreditCardRequired] = Field(
        default=None, description="Closest available time to the requested time"
    )
