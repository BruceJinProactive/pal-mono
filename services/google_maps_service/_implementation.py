import json
import os
import time
from typing import List, Optional

import httpx
from fastapi import HTTPException, status

from services.google_maps_service.schemas import (
    GoogleMapsSearchRequest,
    GoogleMapsSearchResponse,
    OpeningHours,
    PlaceResult,
)
from utils.log import logger

GOOGLE_MAPS_API_BASE_URL = "https://maps.googleapis.com/maps/api"
PLACES_SEARCH_ENDPOINT = "/place/textsearch/json"
PLACE_DETAILS_ENDPOINT = "/place/details/json"
TIMEZONE_ENDPOINT = "/timezone/json"


def _get_api_key() -> str:
    """Get Google Maps API key from environment variables."""
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google Maps API key not configured",
        )
    return api_key


async def _search_places_text(
    query: str,
    location: Optional[str] = None,
    radius: Optional[int] = None,
    language: str = "en",
    region: Optional[str] = None,
) -> dict:
    """
    Perform text search using Google Maps Places API.

    Args:
        query: Search query
        location: Location bias (lat,lng or place name)
        radius: Search radius in meters
        language: Language code
        region: Region code

    Returns:
        Raw API response as dictionary
    """
    api_key = _get_api_key()

    params = {
        "query": query,
        "key": api_key,
        "language": language,
    }

    if location:
        params["location"] = location
    if radius:
        params["radius"] = str(min(radius, 50000))
    if region:
        params["region"] = region

    url = f"{GOOGLE_MAPS_API_BASE_URL}{PLACES_SEARCH_ENDPOINT}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()

        data = response.json()

        return data

    except httpx.HTTPStatusError as e:
        logger.error(f"[GoogleMaps] HTTP error during search: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Google Maps API error: {e.response.status_code}",
        )
    except httpx.RequestError as e:
        logger.error(f"[GoogleMaps] Network error during search: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to Google Maps API",
        )
    except json.JSONDecodeError as e:
        logger.error(f"[GoogleMaps] JSON decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid response from Google Maps API",
        )


async def _get_place_details(place_id: str, language: str = "en") -> dict:
    """
    Get detailed information for a specific place.

    Args:
        place_id: Google Places ID
        language: Language code

    Returns:
        Detailed place information
    """
    api_key = _get_api_key()

    fields = [
        "place_id",
        "name",
        "formatted_address",
        "geometry",
        "formatted_phone_number",
        "international_phone_number",
        "website",
        "opening_hours",
        "business_status",
        "types",
    ]

    params = {
        "place_id": place_id,
        "fields": ",".join(fields),
        "key": api_key,
        "language": language,
    }

    url = f"{GOOGLE_MAPS_API_BASE_URL}{PLACE_DETAILS_ENDPOINT}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10.0)
            response.raise_for_status()

        data = response.json()

        if data.get("status") != "OK":
            logger.warning(
                f"[GoogleMaps] Place details API returned status: {data.get('status')}"
            )
            return {}

        return data.get("result", {})

    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning(f"[GoogleMaps] Failed to get place details for {place_id}: {e}")
        return {}


async def _get_timezone_id(latitude: float, longitude: float) -> Optional[str]:
    """
    Get timezone ID for a location using Google Time Zone API.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate

    Returns:
        Timezone ID (e.g., "America/Los_Angeles") or None if failed
    """
    api_key = _get_api_key()

    # Use current timestamp for timezone lookup
    timestamp = int(time.time())

    params = {
        "location": f"{latitude},{longitude}",
        "timestamp": timestamp,
        "key": api_key,
    }

    url = f"{GOOGLE_MAPS_API_BASE_URL}{TIMEZONE_ENDPOINT}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=5.0)
            response.raise_for_status()

        data = response.json()

        if data.get("status") == "OK":
            return data.get("timeZoneId")
        else:
            logger.warning(
                "[GoogleMaps] Timezone API returned status: %s", data.get("status")
            )
            return None

    except json.JSONDecodeError as e:
        logger.warning("[GoogleMaps] JSON decode error in timezone API: %s", e)
        return None
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning("[GoogleMaps] Failed to get timezone: %s", e)
        return None


def _extract_menu_url(place_data: dict) -> Optional[str]:
    """
    Extract menu URL from place data if available.

    This is a heuristic approach since Google Maps doesn't have a dedicated
    menu field. We look for common menu-related keywords in the website URL.
    """
    website = place_data.get("website")
    if not website:
        return None

    menu_indicators = ["menu", "food", "dining", "order", "delivery"]
    website_lower = website.lower()

    if any(indicator in website_lower for indicator in menu_indicators):
        return website

    place_types = place_data.get("types", [])
    restaurant_types = ["restaurant", "food", "meal_takeaway", "meal_delivery"]

    if any(rest_type in place_types for rest_type in restaurant_types):
        return website

    return None


async def _convert_to_place_result(
    place_data: dict, detailed_data: Optional[dict] = None
) -> PlaceResult:
    """
    Convert Google Maps API response to PlaceResult schema.

    Args:
        place_data: Basic place data from search
        detailed_data: Detailed place data from place details API

    Returns:
        PlaceResult object
    """
    data = detailed_data if detailed_data else place_data

    timezone_id = None
    geometry = data.get("geometry")
    if geometry and "location" in geometry:
        location = geometry["location"]
        if "lat" in location and "lng" in location:
            timezone_id = await _get_timezone_id(location["lat"], location["lng"])

    opening_hours_data = data.get("opening_hours")
    opening_hours = None
    if opening_hours_data:
        opening_hours = OpeningHours(
            open_now=opening_hours_data.get("open_now"),
            periods=opening_hours_data.get("periods"),
            weekday_text=opening_hours_data.get("weekday_text"),
        )

    menu_url = _extract_menu_url(data)

    return PlaceResult(
        place_id=data.get("place_id", ""),
        name=data.get("name", ""),
        formatted_address=data.get("formatted_address", ""),
        geometry=data.get("geometry"),
        timezone_id=timezone_id,
        formatted_phone_number=data.get("formatted_phone_number"),
        international_phone_number=data.get("international_phone_number"),
        website=data.get("website"),
        opening_hours=opening_hours,
        business_status=data.get("business_status"),
        types=data.get("types"),
        menu_url=menu_url,
    )


async def search_places_by_name(
    request: GoogleMapsSearchRequest,
) -> GoogleMapsSearchResponse:
    """
    Search for places by name using Google Maps Places API.

    Args:
        request: Search request parameters

    Returns:
        GoogleMapsSearchResponse with list of places

    Raises:
        HTTPException: If the search fails
    """
    try:
        search_data = await _search_places_text(
            query=request.query,
            location=request.location,
            radius=request.radius,
            language=request.language or "en",
            region=request.region,
        )

        if search_data.get("status") != "OK":
            error_message = search_data.get(
                "error_message", f"API returned status: {search_data.get('status')}"
            )
            logger.error(f"[GoogleMaps] API error: {error_message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=error_message
            )

        search_results = search_data.get("results", [])
        place_results: List[PlaceResult] = []

        for place_data in search_results:
            place_id = place_data.get("place_id")
            if not place_id:
                continue

            detailed_data = await _get_place_details(place_id, request.language or "en")

            place_result = await _convert_to_place_result(place_data, detailed_data)
            place_results.append(place_result)

        return GoogleMapsSearchResponse(
            results=place_results,
            status="OK",
            next_page_token=search_data.get("next_page_token"),
            total_results=len(place_results),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GoogleMaps] Unexpected error during search: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while searching places",
        )
