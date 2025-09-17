from typing import List, Optional

from pydantic import BaseModel, Field


class GoogleMapsSearchRequest(BaseModel):
    """Request schema for Google Maps place search by name."""

    query: str = Field(..., description="The name or query to search for places")
    location: Optional[str] = Field(
        None, description="Location bias (latitude,longitude or place name)"
    )
    radius: Optional[int] = Field(
        None, description="Search radius in meters (max 100000)"
    )
    language: Optional[str] = Field("en", description="Language code for results")
    region: Optional[str] = Field(
        None, description="Region code for results (e.g., 'us', 'ca')"
    )


class OpeningHours(BaseModel):
    """Opening hours information for a place."""

    open_now: Optional[bool] = Field(
        None, description="Whether the place is currently open"
    )
    periods: Optional[List[dict]] = Field(None, description="Weekly opening hours")
    weekday_text: Optional[List[str]] = Field(
        None, description="Human-readable opening hours"
    )


class PlaceResult(BaseModel):
    """Individual place result from Google Maps search."""

    place_id: str = Field(..., description="Unique Google Places identifier")
    name: str = Field(..., description="Business name")
    formatted_address: str = Field(..., description="Full formatted address")
    geometry: Optional[dict] = Field(
        None, description="Location geometry data from Google Places API"
    )
    timezone_id: Optional[str] = Field(
        None, description="Timezone ID (e.g., 'America/Los_Angeles')"
    )
    formatted_phone_number: Optional[str] = Field(
        None, description="Formatted phone number"
    )
    international_phone_number: Optional[str] = Field(
        None, description="International phone number format"
    )
    website: Optional[str] = Field(None, description="Business website URL")
    opening_hours: Optional[OpeningHours] = Field(
        None, description="Opening hours information"
    )
    business_status: Optional[str] = Field(
        None, description="Business operational status"
    )
    types: Optional[List[str]] = Field(None, description="Place types")
    menu_url: Optional[str] = Field(None, description="Menu URL if available")


class GoogleMapsSearchResponse(BaseModel):
    """Response schema for Google Maps place search."""

    results: List[PlaceResult] = Field(..., description="List of found places")
    status: str = Field(..., description="API response status")
    next_page_token: Optional[str] = Field(
        None, description="Token for next page of results"
    )
    total_results: int = Field(..., description="Total number of results found")


class GoogleMapsErrorResponse(BaseModel):
    """Error response schema for Google Maps API."""

    error: str = Field(..., description="Error message")
    status: str = Field(..., description="Error status code")
    details: Optional[str] = Field(None, description="Additional error details")
