from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

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
    decoded_body: str


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


class CancellationPolicyType(str, Enum):
    """Types of cancellation policies"""

    DEPOSIT = "Deposit"
    HOLD = "Hold"


class DepositType(str, Enum):
    """Types of deposits"""

    PER_GUEST = "PerGuest"
    FLAT_FEE = "FlatFee"


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

    type: CancellationPolicyType
    id: str
    amount: Optional[int] = None
    denominator: Optional[int] = None
    currency: Optional[str] = None
    deposit_type: Optional[DepositType] = Field(None, alias="depositType")


class DiningAreaAttribute(BaseModel):
    """Attributes of a dining area"""

    id: int
    attributes: str
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
