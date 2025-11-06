"""URL shortening utility using TinyURL service."""

import os

import requests

from utils.log import logger
from utils.secret import get_server_secret

DEFAULT_TIMEOUT = 10
TINYURL_API_URL = "https://api.tinyurl.com/create"


def shorten_url(long_url: str) -> str:
    """
    Shorten a URL using TinyURL service.

    Args:
        long_url: The URL to shorten

    Returns:
        Shortened URL, or the original URL if shortening fails
    """

    api_token = get_server_secret("TINYURL_API_KEY")

    if not api_token:
        logger.debug("[ShortenUrl] No API token available for URL shortening")
        return long_url

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {api_token}",
    }

    payload = {"url": long_url}

    # Add domain if specified in environment variable
    domain = os.getenv("TINYURL_DOMAIN_NAME")
    if domain:
        payload["domain"] = domain

    logger.debug(f"[ShortenUrl] Attempting to shorten URL: {long_url}")

    for attempt in range(2):  # Try twice (original + 1 retry)
        try:
            logger.debug(f"[ShortenUrl] URL shortening attempt {attempt + 1}/2")
            response = requests.post(
                TINYURL_API_URL, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT
            )

            if response.status_code == 200:
                data = response.json()
                shortened_url = data.get("data", {}).get("tiny_url")
                if shortened_url:
                    logger.debug(
                        f"[ShortenUrl] Successfully shortened URL: {shortened_url}"
                    )
                    return shortened_url
                else:
                    logger.debug(
                        "[ShortenUrl] API returned 200 but no tiny_url in response."
                    )
            else:
                logger.debug(
                    f"[ShortenUrl] TinyURL API returned status {response.status_code}"
                )

        except Exception as e:
            logger.debug(
                f"[ShortenUrl] Exception during URL shortening attempt {attempt + 1}: {str(e)}"
            )
            continue

    logger.debug("[ShortenUrl] URL shortening failed, returning original URL")
    return long_url
