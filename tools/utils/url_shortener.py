"""URL shortening utility using TinyURL service."""

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import requests

from api.settings import ApiSettings
from utils.log import logger
from utils.secret import get_server_secret_with_fallback

DEFAULT_TIMEOUT = 10
TINYURL_API_URL = "https://api.tinyurl.com/create"
ENV_URL_PREFIXES = {"lat", "stg"}


def _apply_env_url_prefix(long_url: str) -> str:
    runtime_env = ApiSettings().runtime_env
    if runtime_env not in ENV_URL_PREFIXES:
        return long_url

    prefix = f"{runtime_env}-"
    url_parts = urlsplit(long_url)
    if url_parts.netloc.startswith(prefix):
        return long_url

    prefixed_netloc = f"{prefix}{url_parts.netloc}"
    return urlunsplit(url_parts._replace(netloc=prefixed_netloc))


def shorten_url(long_url: str, *, use_env_url_prefix: bool = False) -> str:
    """
    Shorten a URL using TinyURL service.

    Args:
        long_url: The URL to shorten
        use_env_url_prefix: Whether to prefix the destination URL host with the
            current runtime environment for non-production links.

    Returns:
        Shortened URL, or the original URL if shortening fails
    """

    api_token = get_server_secret_with_fallback("TINYURL_API_KEY")

    if not api_token:
        logger.debug("[ShortenUrl] No API token available for URL shortening")
        return long_url

    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {api_token}",
    }

    if use_env_url_prefix:
        long_url = _apply_env_url_prefix(long_url)

    payload = {"url": long_url}

    # Add domain if specified in environment variable
    domain = os.getenv("TINYURL_DOMAIN_NAME")
    if domain:
        payload["domain"] = domain

    # Add expires_at if EXPIRES_IN_MINS is set
    expires_mins_str = os.getenv("EXPIRES_IN_MINS")
    if expires_mins_str:
        try:
            expires_mins = int(expires_mins_str)
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_mins)
            payload["expires_at"] = expires_at.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            logger.debug(
                "[ShortenUrl] Invalid EXPIRES_IN_MINS value, skipping expiration"
            )

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
