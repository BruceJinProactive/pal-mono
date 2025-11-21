"""Utilities for discovering the current Resy API key from production bundles."""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from utils.log import logger

_BUNDLE_SRC_PATTERN = re.compile(
    r'(?:src|href)=(?:"|\')(?P<src>(?:\.\./|\./)?modules/app[^"\']*?\.js(?:\?[^"\']*)?)(?:"|\')'
)
_API_KEY_PATTERN = re.compile(r'apiKey"?\s*:\s*["\']([^"\'\\]+)["\']')

_VENUE_PAGE_TEMPLATE = "https://resy.com/cities/{city}/venues/{venue}"

_CACHE_TTL_SECONDS = 60 * 60  # 1 hour
_DEFAULT_USER_AGENT = "pal-mono/1.0"


@dataclass
class _CachedKey:
    api_key: str
    bundle_url: str
    etag: Optional[str]
    last_modified: Optional[str]
    fetched_at: float


_CACHE: Optional[_CachedKey] = None
_ORIGINAL_API_KEY = "VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"
_WARNED_KEY_MISMATCH = False


def get_resy_api_key(
    *,
    city: str,
    venue_name: str,
    timeout: int = 30,
    user_agent: str = _DEFAULT_USER_AGENT,
) -> str:
    """Return the current Resy API key, refreshing from the live bundle when needed."""

    global _CACHE
    now = time.time()

    if _CACHE and now - _CACHE.fetched_at < _CACHE_TTL_SECONDS:
        return _CACHE.api_key

    try:
        bundle_url = _discover_bundle_url(
            city=city, venue_name=venue_name, timeout=timeout, user_agent=user_agent
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[Resy API] Failed to discover bundle URL", exc_info=True)
        if _CACHE:
            return _CACHE.api_key
        raise RuntimeError(
            "Unable to locate Resy bundle for API key extraction"
        ) from exc

    etag = last_modified = None
    if _CACHE and _CACHE.bundle_url == bundle_url:
        etag = _CACHE.etag
        last_modified = _CACHE.last_modified

    try:
        bundle_text, new_etag, new_last_modified = _fetch_bundle(
            bundle_url=bundle_url,
            etag=etag,
            last_modified=last_modified,
            timeout=timeout,
            user_agent=user_agent,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[Resy API] Failed to fetch bundle", exc_info=True)
        if _CACHE:
            return _CACHE.api_key
        raise RuntimeError(
            "Unable to download Resy bundle for API key extraction"
        ) from exc

    if bundle_text is None:
        # Not modified; reuse cached key but refresh timestamp and headers.
        if not _CACHE:
            raise RuntimeError("Resy bundle responded 304 but no cached key available")
        _CACHE = _CachedKey(
            api_key=_CACHE.api_key,
            bundle_url=bundle_url,
            etag=new_etag or _CACHE.etag,
            last_modified=new_last_modified or _CACHE.last_modified,
            fetched_at=now,
        )
        return _CACHE.api_key

    api_key = _extract_api_key(bundle_text)
    if not api_key:
        logger.error("[Resy API] Unable to locate apiKey inside bundle %s", bundle_url)
        if _CACHE:
            return _CACHE.api_key
        raise RuntimeError("Resy apiKey not found in bundle")

    global _WARNED_KEY_MISMATCH
    if api_key != _ORIGINAL_API_KEY and not _WARNED_KEY_MISMATCH:
        logger.warning(
            "[Resy API] Extracted apiKey differs from the original reference key."
        )
        _WARNED_KEY_MISMATCH = True

    _CACHE = _CachedKey(
        api_key=api_key,
        bundle_url=bundle_url,
        etag=new_etag,
        last_modified=new_last_modified,
        fetched_at=now,
    )
    return api_key


def _discover_bundle_url(
    *, city: str, venue_name: str, timeout: int, user_agent: str
) -> str:
    page_url = _VENUE_PAGE_TEMPLATE.format(city=city, venue=venue_name)
    body, _, _ = _fetch_text(page_url, timeout=timeout, user_agent=user_agent)

    match = _BUNDLE_SRC_PATTERN.search(body)
    if not match:
        raise RuntimeError("Unable to locate Resy app bundle in venue page")

    src = match.group("src")
    if src.startswith("modules/"):
        src = f"/{src}"
    return urllib.parse.urljoin(page_url, src)


def _fetch_bundle(
    *,
    bundle_url: str,
    etag: Optional[str],
    last_modified: Optional[str],
    timeout: int,
    user_agent: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    headers = {"User-Agent": user_agent}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    try:
        body, new_etag, new_last_modified = _fetch_text(
            bundle_url, timeout=timeout, user_agent=user_agent, headers=headers
        )
        return body, new_etag, new_last_modified
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None, exc.headers.get("ETag"), exc.headers.get("Last-Modified")
        raise


def _fetch_text(
    url: str,
    *,
    timeout: int,
    user_agent: str,
    headers: Optional[dict[str, str]] = None,
) -> tuple[str, Optional[str], Optional[str]]:
    request_headers = {"User-Agent": user_agent}
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding", "").lower() == "gzip":
            import gzip

            raw = gzip.decompress(raw)

        body = raw.decode("utf-8", errors="replace")
        info = response.info()
        return body, info.get("ETag"), info.get("Last-Modified")


def _extract_api_key(bundle_text: str) -> Optional[str]:
    match = _API_KEY_PATTERN.search(bundle_text)
    if match:
        return match.group(1)
    return None
