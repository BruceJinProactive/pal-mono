from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, EmailStr, Field

TIMEZONE = ZoneInfo("America/Los_Angeles")


######### OpenTable API CLASS START ############
class HttpMethod(str, Enum):
    """HTTP methods for API requests"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class OpenTableResponse(BaseModel):
    """Class to handle OpenTable API response data"""

    status: int
    reason: str
    decoded_body: Dict[str, Any]


class OpenTableAccessToken(BaseModel):
    """
    This class represents the response from the OpenTable Authentication API.
    It contains the access token used to authenticate subsequent API calls.
    """

    access_token: str
    expires_in: int
    token_type: str
    scope: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(TIMEZONE))


class OpenTableRestaurantInfo(BaseModel):
    """
    RestaurantInfo object returned from the OpenTable API.
    """

    rid: int = Field(description="Restaurant ID")
    name: str = Field(description="Restaurant name")
    address: str = Field(description="Restaurant address")
    city: str = Field(description="Restaurant city")
    state: str = Field(description="Restaurant state")
    postal_code: str = Field(description="Restaurant postal/zip code")
    country: str = Field(description="Restaurant country")
    phone: str = Field(description="Restaurant phone number")
    latitude: float = Field(description="Restaurant latitude")
    longitude: float = Field(description="Restaurant longitude")
    cuisine_types: List[str] = Field(description="Restaurant cuisine types")
    price_range: str = Field(description="Restaurant price range")
    website: Optional[str] = Field(None, description="Restaurant website")
    hours: Dict[str, str] = Field(description="Restaurant operating hours")


# ---- Availability Search API Models ----


class TableAttribute(str, Enum):
    """Possible table attributes for the search"""

    DEFAULT = "default"
    HIGHTOP = "hightop"
    BAR = "bar"
    COUNTER = "counter"
    OUTDOOR = "outdoor"


class EnvironmentType(str, Enum):
    """Types of dining environments"""

    INDOOR = "Indoor"
    OUTDOOR = "Outdoor"


class NoAvailabilityReason(str, Enum):
    """Reasons why no availability might exist"""

    NO_TIMES_EXIST = "NoTimesExist"
    BELOW_MIN_PARTY_SIZE = "BelowMinPartySize"
    ABOVE_MAX_PARTY_SIZE = "AboveMaxPartySize"
    OUTSIDE_BOOKING_WINDOW = "OutsideBookingWindow"


class CancellationPolicy(BaseModel):
    """Details of the cancellation policy"""

    type: str
    id: str
    amount: Optional[int] = None
    denominator: Optional[int] = None
    currency: Optional[str] = None
    deposit_type: Optional[str] = Field(None, alias="depositType")


class DiningAreaAttribute(BaseModel):
    """Attributes of a dining area"""

    id: int
    attributes: List[str]
    environment: EnvironmentType
    booking_url: Optional[str] = Field(None, alias="booking_url")
    booking_restref_url: Optional[str] = Field(None, alias="booking_restref_url")
    experience_ids: Optional[List[int]] = Field(None, alias="experience_ids")


class AvailabilityType(BaseModel):
    """Types of availability"""

    type: str
    cancellation_policy: Optional[CancellationPolicy] = Field(
        None, alias="cancellationPolicy"
    )
    dining_area: Optional[List[DiningAreaAttribute]] = Field(None, alias="diningArea")


class TimeAvailable(BaseModel):
    """Detailed availability for each time slot"""

    time: str
    availability_types: List[AvailabilityType] = Field(alias="availability_types")


class AvailabilitySearchRequest(BaseModel):
    """Request parameters for availability search"""

    start_date_time: str = Field(
        description="The local date and time to begin the search (ISO 8601 format)"
    )
    forward_minutes: int = Field(
        description="Minutes forward from start time to search (up to 720)"
    )
    backward_minutes: int = Field(
        description="Minutes backward from start time to search (up to 720)"
    )
    party_size: int = Field(description="Number of diners")
    require_attributes: Optional[TableAttribute] = Field(
        None, description="Table types for search"
    )
    include_credit_card_results: Optional[bool] = Field(
        None, description="Include availability requiring credit card"
    )
    include_experiences: Optional[bool] = Field(
        False, description="Include special dining experiences"
    )


class AvailabilitySearchResponse(BaseModel):
    """Response from availability search"""

    rid: int
    party_size: int
    times: List[str]
    times_available: List[TimeAvailable] = Field(alias="times_available")
    no_availability_reasons: Optional[List[NoAvailabilityReason]] = Field(
        None, alias="no_availability_reasons"
    )
    href: Optional[str] = None


# ---- Cancellation Policies API Models ----


class DepositDetails(BaseModel):
    """Details of the deposit for cancellation policy"""

    amount: int = Field(description="Deposit amount in minor currency units")
    currency: str = Field(description="Currency of the deposit amount")
    denominator: int = Field(description="Conversion factor for minor units")
    type: str = Field(description="Specifies if the deposit is per guest")


class CutoffPolicy(BaseModel):
    """Cutoff policy details"""

    cutoff_type: str = Field(alias="cutoffType", description="Type of cutoff applied")
    days_before_cutoff: int = Field(
        alias="daysBeforeCutoff", description="Number of days before cutoff"
    )


class CancellationPolicyDetails(BaseModel):
    """Response from the Cancellation Policies API"""

    party_size: int = Field(
        alias="partySize", description="The number of guests for the reservation"
    )
    policy_type: str = Field(
        alias="policyType", description="Type of cancellation policy"
    )
    deposit_details: DepositDetails = Field(
        alias="depositDetails", description="Details of the deposit policy"
    )
    cut_off: CutoffPolicy = Field(alias="cutOff", description="Cutoff policy details")


# ---- Availability Metadata API Models ----


class DiningArea(BaseModel):
    """Detailed information about available dining areas"""

    id: int = Field(description="Identifier of the dining area")
    name: str = Field(description="Name of the dining area")
    description: str = Field(description="Description of the dining area")
    environment: Optional[EnvironmentType] = Field(
        None, description="Environment type (e.g., Indoor, Outdoor)"
    )


class AvailabilityMetadataData(BaseModel):
    """Data object in the Availability Metadata response"""

    environments: List[EnvironmentType] = Field(
        description="Available environment types"
    )
    attributes: List[TableAttribute] = Field(description="Available table attributes")
    dining_areas: List[DiningArea] = Field(
        description="Detailed information about available dining areas"
    )


class AvailabilityMetadataResponse(BaseModel):
    """Response from the Availability Metadata API"""

    data: AvailabilityMetadataData


# ---- Slot Locks API Models ----


class PriceSizeType(BaseModel):
    """Price type for a specific party size"""

    id: int = Field(description="Unique identifier for the price type")
    count: int = Field(description="Count of items for the price type")


class AddOn(BaseModel):
    """Add-on item for an experience"""

    item_id: str = Field(description="Unique identifier for the add-on item")
    quantity: int = Field(description="Quantity of the add-on item")


class Experience(BaseModel):
    """Details about the dining experience"""

    id: int = Field(description="Unique identifier for the experience")
    version: int = Field(description="Version of the experience")
    party_size_per_price_type: Optional[List[PriceSizeType]] = Field(
        None, description="Array detailing the party size per price type"
    )
    add_ons: Optional[List[AddOn]] = Field(
        None, description="Array of add-on items for the experience"
    )


class SlotLockRequest(BaseModel):
    """Request parameters for creating a slot lock"""

    party_size: int = Field(description="Number of people in the reservation party")
    date_time: str = Field(
        description="Date and time of the reservation in ISO 8601 format"
    )
    reservation_attribute: Optional[TableAttribute] = Field(
        None, description="Type or attribute of the reservation (e.g., default)"
    )
    experience: Optional[Experience] = Field(
        None, description="Details about the dining experience"
    )
    dining_area_id: Optional[int] = Field(
        None, description="Identifier for the dining area"
    )
    environment: Optional[EnvironmentType] = Field(
        None, description="Type of environment (e.g., Indoor, Outdoor)"
    )


class SlotLockResponse(BaseModel):
    """Response from the Slot Lock API"""

    expires_at: str = Field(
        description="The expiration date and time of the slot lock in ISO 8601 format"
    )
    reservation_token: str = Field(
        description="A unique token required for the subsequent reservation creation request"
    )


# ---- Reservation API Models ----


class PhoneObject(BaseModel):
    """Phone information for the reservation"""

    number: str = Field(description="The phone number of the guest")
    country_code: str = Field(description="The country code for the number")
    phone_type: str = Field(description="The type of phone (e.g., Mobile)")


class CreditCardObject(BaseModel):
    """Credit card details for the reservation"""

    token: str = Field(description="A token representing the credit card")
    last4: str = Field(description="The last four digits of the credit card")


class ReservationRequest(BaseModel):
    """Request parameters for creating a reservation"""

    reservation_token: str = Field(
        description="A unique token identifying the temporary hold on a table from a previous call"
    )
    first_name: str = Field(
        description="The first name of the guest making the reservation"
    )
    last_name: str = Field(
        description="The last name of the guest making the reservation"
    )
    email_address: EmailStr = Field(description="The email address of the guest")
    phone: PhoneObject = Field(description="The guest's phone number")
    reservation_attribute: TableAttribute = Field(
        description="The seating option (default, hightop, bar, counter, outdoor)"
    )
    special_request: Optional[str] = Field(
        None, description="Any special requests for the reservation"
    )
    credit_card: Optional[CreditCardObject] = Field(
        None, description="Credit card details for the reservation"
    )
    login_name: Optional[str] = Field(
        None, description="Used for concierge/referral details"
    )
    restaurant_email_marketing_opt_in: bool = Field(
        description="If true, opts the guest into email marketing by the restaurant"
    )
    sms_notifications_opt_in: Optional[bool] = Field(
        False, description="If true, the guest opts in to receive SMS notifications"
    )
    dining_area_id: int = Field(description="The unique identifier for the dining area")
    environment: EnvironmentType = Field(
        description="The environment for the dining experience (e.g., Indoor, Outdoor)"
    )
    experience: Optional[Experience] = Field(
        None, description="Experience details for the reservation"
    )


class ReservationResponse(BaseModel):
    """Response from the Reservation API"""

    message: str = Field(description="Booking policy details for the reservation")
    confirmation_number: int = Field(
        description="Unique identifier for the confirmed reservation"
    )
    offer_confirmation_number: int = Field(
        description="Unique identifier for any special offer linked to the reservation"
    )
    date_time: str = Field(
        description="Date and time of the reservation in ISO 8601 format"
    )
    party_size: int = Field(description="Number of guests included in the reservation")
    notes: Optional[str] = Field(
        None, description="Special requests or notes provided during the reservation"
    )
    manage_reservation_url: str = Field(
        description="URL to manage the confirmed reservation online"
    )


######### OpenTable API CLASS END ############


class SubQueries(BaseModel):
    queries: list[str] = Field(
        description=(
            "Decompose the chat history into individual order items. For example,"
            "If the chat history is 'I would like to order a pizza with extra cheese "
            "and pickles, burger, and salad, for takeout.' The return would be ['pizza', "
            "'burger', 'salad']\n\n"
            "DO NOT include modifications (e.g. extra cheese, pickles)."
        ),
    )
