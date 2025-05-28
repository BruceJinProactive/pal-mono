from typing import List, Optional

from pydantic import BaseModel, Field


class YelpApiResponse(BaseModel):
    """Class to handle Yelp API response data"""

    status: int
    reason: str
    decoded_body: dict


######### YELP BOOKINGS API CLASSES START ############


class YelpBookingsOpeningsRequest(BaseModel):
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


class YelpBookingsHoldsRequest(BaseModel):
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


class YelpBookingsHoldsResponse(BaseModel):
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


class YelpBookingsReservationsRequest(BaseModel):
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


class YelpBookingsReservationsResponse(BaseModel):
    """Response from Yelp Bookings reservations endpoint"""

    confirmation_url: str = Field(
        description="URL to view the confirmed reservation on Yelp's platform"
    )
    notes: str = Field(description="Additional notes for the reservation")
    reservation_id: str = Field(
        description="Unique identifier for the confirmed reservation"
    )


######### YELP BOOKINGS API CLASSES END ############


######### YELP PARTNER API CLASSES START ############


class YelpAccessTokenRequest(BaseModel):
    """Request parameters for Yelp Partner API access token endpoint"""

    client_id: str = Field(
        description="ID assigned by Yelp for the third-party system that will make user-authorized requests to Yelp."
    )
    client_secret: str = Field(
        description="Client secret assigned by Yelp for the third-party system that will make user-authorized requests to Yelp."
    )
    code: str = Field(
        description="A unique code that will be used by the client to redeem an access token."
    )
    grant_type: str = Field(
        description="The grant being presented in order to exchange for an access token. For example, when redeeming the authorization code for an access token, this value will be authorization_code."
    )
    redirect_uri: Optional[str] = Field(
        default=None,
        description="The client-provided redirect endpoint URL. If no redirect_uri was provided during authorization, it is optional here.",
    )


class YelpAccessTokenResponse(BaseModel):
    """Response from Yelp Partner API access token endpoint"""

    access_token: str = Field(
        description="The access token that can be used to make authorized requests to Yelp APIs"
    )
    token_type: str = Field(description="The type of token, typically 'Bearer'")
    expires_in: Optional[int] = Field(
        default=None, description="The lifetime in seconds of the access token"
    )
    refresh_token: Optional[str] = Field(
        default=None,
        description="The refresh token that can be used to obtain new access tokens",
    )
    scope: Optional[str] = Field(
        default=None, description="The scope of the access token"
    )


######### YELP PARTNER API CLASSES END ############
