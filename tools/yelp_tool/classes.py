from typing import List, Optional

from pydantic import BaseModel, Field

######### YELP BOOKINGS API CLASSES START ############


class YelpBookingsOpeningsRequest(BaseModel):
    """Request parameters for Yelp Bookings openings endpoint"""

    # Path parameter
    business_id_or_alias: str = Field(
        description="A unique identifier for a Yelp Business. Can be either a 22-character Yelp Business ID, or a Yelp Business Alias."
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


class YelpBookingsOpeningsResponse(BaseModel):
    """Response from Yelp Bookings openings endpoint"""

    reservation_times: List[DailyReservationTimes] = Field(
        description="Available reservation times across multiple days (typically 4 days: day before, current day, and 2 days after requested date)"
    )
    covers_range: Optional[CoversRange] = Field(
        default=None,
        description="Range of party sizes supported (included when get_covers_range=true)",
    )


######### YELP BOOKINGS API CLASSES END ############
