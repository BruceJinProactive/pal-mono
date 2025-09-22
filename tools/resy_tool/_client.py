"""Lightweight Resy API client for availability search."""

import json
import urllib.request
from typing import Any, Dict

from tools.resy_tool._apikey import get_resy_api_key
from utils.log import logger

RESY_API_URL = "https://api.resy.com/4/find"
USER_AGENT = "pal-mono/1.0"


def find_resy_availability(
    *,
    venue_id: int,
    city: str,
    venue_name: str,
    day: str,
    party_size: int,
    time_filter: str,
    latitude: float = 0.0,
    longitude: float = 0.0,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Call the public Resy /4/find endpoint and return the parsed JSON body."""

    api_key = get_resy_api_key(
        city=city, venue_name=venue_name, timeout=timeout, user_agent=USER_AGENT
    )

    payload = {
        "lat": latitude,
        "long": longitude,
        "day": day,
        "party_size": party_size,
        "venue_id": venue_id,
        "time_filter": time_filter,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f'ResyAPI api_key="{api_key}"',
        "User-Agent": USER_AGENT,
    }

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        RESY_API_URL, data=data, headers=headers, method="POST"
    )

    logger.debug(
        "[Resy API] find availability",
        extra={
            "venue_id": venue_id,
            "day": day,
            "party_size": party_size,
            "time_filter": time_filter,
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")

    return json.loads(body or "{}")
