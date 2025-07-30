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


######### YELP BOOKINGS API CLASSES START (CREDIT CARD NOT REQUIRED) ############


class YelpBookingsOpeningsRequestCreditCardNotRequired(BaseModel):
    """Request parameters for Yelp Bookings openings endpoint"""

    # Path parameter
    business_id_or_alias: str = Field(
        pattern=r"^(?:[A-Za-z0-9]{22}|[A-Za-z0-9-]{1,255})$",
        description="Either a 22-char Yelp Business ID or a valid business alias.",
    )

    # Query parameters
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
        description="The time of the requested reservation, format is HH:MM",
        pattern=r"^\d{2}:\d{2}$",
    )
    get_covers_range: Optional[bool] = Field(
        default=None,
        description="If true, include the covers_range dict in the response.",
    )
    num_results_after: Optional[int] = Field(
        default=None,
        description="Set to 0 if user wants to know the openings before the current result, otherwise don't include this field",
    )
    num_results_before: Optional[int] = Field(
        default=None,
        description="Set to 0 if user wants to know the openings after the current result, otherwise don't include this field",
    )


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


class YelpBookingsHoldsRequestCreditCardNotRequired(BaseModel):
    """Request parameters for Yelp Bookings holds endpoint"""

    # Path parameter
    business_id_or_alias: str = Field(
        pattern=r"^(?:[A-Za-z0-9]{22}|[A-Za-z0-9-]{1,255})$",
        description="Either a 22-char Yelp Business ID or a valid business alias.",
    )

    # Body parameters (sent as form data)
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
        description="The time of the requested reservation, format is HH:MM",
        pattern=r"^\d{2}:\d{2}$",
    )
    unique_id: str = Field(
        description="User's device id or unique user id to help tie together actions of the user on the API. Multiple requests to the Holds endpoint by the same user should use the same unique_id.",
        max_length=300,
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


class YelpBookingsReservationsRequestCreditCardNotRequired(BaseModel):
    """Request parameters for Yelp Bookings reservations endpoint"""

    # Path parameter
    business_id_or_alias: str = Field(
        pattern=r"^(?:[A-Za-z0-9]{22}|[A-Za-z0-9-]{1,255})$",
        description="Either a 22-char Yelp Business ID or a valid business alias.",
    )

    # Body parameters (sent as form data)
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
        description="The time of the requested reservation, format is HH:MM",
        pattern=r"^\d{2}:\d{2}$",
    )
    first_name: str = Field(
        description="The first name of the person making the reservation."
    )
    last_name: str = Field(
        description="The last name of the person making the reservation."
    )
    phone: str = Field(
        description="The phone number to attach to the reservation.",
        min_length=1,
        max_length=32,
    )
    email: str = Field(description="The email to attach to the reservation.")
    hold_id: str = Field(description="The Hold ID returned from the Holds endpoint.")
    unique_id: str = Field(
        description="User's device id or unique user id to help tie together actions of the user on the API. Multiple requests to the Holds endpoint by the same user should use the same unique_id.",
        max_length=300,
    )
    notes: Optional[str] = Field(
        default=None, description="The additional party notes for the reservation."
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


######### YELP BOOKINGS API CLASSES END (CREDIT CARD NOT REQUIRED) ############


######### YELP WAITLIST API CLASSES START ############


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


class YelpWaitlistStatusRequest(BaseModel):
    """Request parameters for Yelp Waitlist Status endpoint"""

    # Path parameter
    business_id: str = Field(
        description="Encrypted Yelp business identifier", min_length=1, max_length=255
    )


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


class YelpWaitlistInfoRequest(BaseModel):
    """Request parameters for Yelp Waitlist Info endpoint"""

    # Path parameter
    business_id: str = Field(
        description="Encrypted Yelp business identifier", min_length=1, max_length=255
    )


class YelpWaitlistInfoResponse(BaseModel):
    """Response from Yelp Waitlist Info endpoint"""

    join_radius: int = Field(description="The maximum join radius", ge=0)
    join_radius_unit: str = Field(description="Join radius unit (miles or kilometers)")
    max_party_size: int = Field(description="The maximum party size", gt=0)
    seating_areas: dict[str, str] = Field(
        description="The seating areas supported by the restaurant (key-value pairs where key is the area code and value is the display name)"
    )


class YelpWaitlistOnMyWayRequest(BaseModel):
    """Request parameters for Yelp Waitlist On-My-Way endpoint"""

    # Path parameter
    business_id: str = Field(
        description="Encrypted Yelp business identifier", min_length=1, max_length=255
    )

    # Body parameters
    phone: str = Field(
        description="Patron's phone number in E.164 format (e.g., +19050000000)",
        pattern=r"^\+[1-9]\d{1,14}$",
    )
    party_size: int = Field(description="Number of guests in the party", gt=0)
    name: str = Field(description="Patron's name", min_length=1)
    arrival_range_max: int = Field(
        description="Patron's expected maximum arrival time (in minutes). Must be 30 minutes from now or earlier. Should be the upper bound of the arrival estimate selected.",
        ge=1,
        le=30,
    )
    arrival_range_min: int = Field(
        description="Patron's expected minimum arrival time (in minutes). Must be 30 minutes from now or earlier.",
        ge=1,
        le=30,
    )
    party_notes: Optional[str] = Field(
        default=None,
        description="Notes from the patron. Will be visible to the host in the host app.",
    )


class YelpWaitlistOnMyWayResponse(BaseModel):
    """Response from Yelp Waitlist On-My-Way endpoint"""

    visit_id: str = Field(description="Encrypted visit identifier")
    party_size: int = Field(description="The number of the guests in the visit", gt=0)
    arrive_by_time: int = Field(
        description="Unix timestamp (seconds) when the guest should be told to arrive at the restaurant"
    )


class WaitlistValidationErrorCode(str, Enum):
    """Error codes for 422 validation errors in waitlist API responses"""

    ALREADY_IN_LINE = "ALREADY_IN_LINE"
    INVALID_ETA = "INVALID_ETA"
    CURRENTLY_HAS_WAIT = "CURRENTLY_HAS_WAIT"
    PARTY_SIZE_TOO_LARGE = "PARTY_SIZE_TOO_LARGE"
    RESTAURANT_NOT_OPEN = "RESTAURANT_NOT_OPEN"
    REMOTE_ENTRY_DENIED = "REMOTE_ENTRY_DENIED"
    SCHEDULE_CONFLICT = "SCHEDULE_CONFLICT"

    def get_description(self) -> str:
        """Get human-readable description for the 422 validation error code"""
        descriptions = {
            "ALREADY_IN_LINE": "Invalid state. The phone number is already in line",
            "INVALID_ETA": "Expected arrival time too far in the past or future. Must be 30 minutes from now or earlier",
            "CURRENTLY_HAS_WAIT": "On My Way visit creation is ineligible, there is currently a wait for the restaurant",
            "PARTY_SIZE_TOO_LARGE": "Party size too large",
            "RESTAURANT_NOT_OPEN": "Restaurant is not open",
            "REMOTE_ENTRY_DENIED": "Restaurant does not allow remote entry",
            "SCHEDULE_CONFLICT": "Special event at restaurant",
        }
        return descriptions.get(self.value, "Description not available")


class YelpWaitlistError(BaseModel):
    """Error object within Yelp Waitlist error responses"""

    code: str = Field(description="The error code")
    description: str = Field(description="The description of the error")

    @classmethod
    def for_validation_error(
        cls, error_code: WaitlistValidationErrorCode
    ) -> "YelpWaitlistError":
        """Create error object for 422 validation errors"""
        return cls(code=error_code.value, description=error_code.get_description())


class YelpWaitlistErrorResponse(BaseModel):
    """Error response from Yelp Waitlist endpoints"""

    error: YelpWaitlistError = Field(description="Error details")


######### YELP WAITLIST API CLASSES END ############


######### LLM EXTRACTION CLASSES START ############


class OpeningsQuery(BaseModel):
    """Extracted parameters for searching restaurant openings - mirrors YelpBookingsOpeningsRequest with optional fields"""

    covers: Optional[int] = Field(
        default=None,
        description="How many people are attending the reservation (min. value is 1; max value is 10).",
        ge=1,
        le=10,
    )
    date: Optional[str] = Field(
        default=None,
        description="The date for the reservation, format is YYYY-mm-dd",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    time: Optional[str] = Field(
        default=None,
        description="The time of the requested reservation, format is HH:MM",
        pattern=r"^\d{2}:\d{2}$",
    )
    get_covers_range: Optional[bool] = Field(
        default=False,
        description="If true, include the covers_range dict in the response.",
    )
    after: Optional[bool] = Field(
        default=None,
        description="Set to true if user wants openings after a specific time",
    )
    before: Optional[bool] = Field(
        default=None,
        description="Set to true if user wants openings before a specific time",
    )


class OpeningsQueryWithoutCreditCard(BaseModel):
    """Extracted parameters for searching restaurant openings - mirrors YelpBookingsOpeningsRequest with optional fields"""

    covers: Optional[int] = Field(
        default=None,
        description="How many people are attending the reservation (min. value is 1; max value is 10).",
        ge=1,
        le=10,
    )
    date: Optional[str] = Field(
        default=None,
        description="The date for the reservation, format is YYYY-mm-dd",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    time: Optional[str] = Field(
        default=None,
        description="The time of the requested reservation, format is HH:MM",
        pattern=r"^\d{2}:\d{2}$",
    )
    get_covers_range: Optional[bool] = Field(
        default=False,
        description="If true, include the covers_range dict in the response.",
    )


class ReservationQuery(BaseModel):
    """Extracted parameters for making a restaurant reservation - mirrors YelpBookingsReservationsRequest with optional fields"""

    covers: Optional[int] = Field(
        default=None,
        description="How many people are attending the reservation (min. value is 1; max value is 10).",
        ge=1,
        le=10,
    )
    date: Optional[str] = Field(
        default=None,
        description="The date for the reservation, format is YYYY-mm-dd",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    time: Optional[str] = Field(
        default=None,
        description="The time of the requested reservation, format is HH:MM",
        pattern=r"^\d{2}:\d{2}$",
    )
    first_name: Optional[str] = Field(
        default=None,
        description="The first name of the person making the reservation.",
    )
    last_name: Optional[str] = Field(
        default=None,
        description="The last name of the person making the reservation.",
    )
    phone: Optional[str] = Field(
        default=None,
        description="The phone number to attach to the reservation.",
        min_length=1,
        max_length=32,
    )
    email: Optional[str] = Field(
        default=None, description="The email to attach to the reservation."
    )
    notes: Optional[str] = Field(
        default=None, description="The additional party notes for the reservation."
    )


######### LLM EXTRACTION CLASSES END ############


# YELP CREDIT CARD REQUIRED API CLASSES START


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

    # Query parameters
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
    notify_me_message: Optional[str] = Field(
        default=None, description="Message for notify me functionality"
    )
    notify_me_url: Optional[str] = Field(
        default=None, description="URL for notify me functionality"
    )
    enable_next_available: bool = Field(
        default=False, description="Whether next available feature is enabled"
    )
    motivational_content: Optional[str] = Field(
        default=None, description="Motivational content for booking"
    )
    recovery_profile: Optional[str] = Field(
        default="none", description="Recovery profile for booking"
    )


# YELP CREDIT CARD REQUIRED API CLASSES END
