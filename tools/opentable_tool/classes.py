from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HttpMethod(str, Enum):
    """HTTP methods supported by the OpenTable API client."""

    GET = "GET"
    POST = "POST"


class OpenTableResponse(BaseModel):
    """Normalized OpenTable API response payload."""

    status: int
    reason: str
    decoded_body: Any = Field(default_factory=dict)


class OpenTableAccessToken(BaseModel):
    """Bearer token extracted from the restaurant page."""

    access_token: str
    expires_in: int
    token_type: str
    scope: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AvailabilitySearchRequest(BaseModel):
    """Minimal payload required to search for reservations."""

    start_date_time: str
    party_size: int


class AvailabilitySearchResponse(BaseModel):
    """Subset of availability details used by the tool."""

    rid: int
    party_size: int
    times_available: list[str]
    no_availability_reasons: list[str] | None = None
