from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import httpx

from services.folk_notion_sync._settings import FolkNotionSyncSettings
from utils.secret import get_client_secret_with_fallback


class FolkClient:
    def __init__(
        self,
        settings: FolkNotionSyncSettings,
        *,
        api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._api_key = api_key or get_client_secret_with_fallback("FOLK_API_KEY")
        self._http_client = http_client

    async def get_resource_url(self, resource_url: str) -> dict[str, Any]:
        _validate_resource_url(resource_url, self._settings.folk_base_url)
        return await self._request("GET", resource_url)

    async def get_company(self, company_id: str) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"{self._settings.folk_base_url}/v1/companies/{company_id}",
        )
        return _data_object(data)

    async def update_company(
        self,
        company_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        data = await self._request(
            "PATCH",
            f"{self._settings.folk_base_url}/v1/companies/{company_id}",
            json_payload=payload,
        )
        return _data_object(data)

    async def list_companies(
        self,
        *,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        url = f"{self._settings.folk_base_url}/v1/companies?limit=100"
        items: list[dict[str, Any]] = []
        pages_read = 0
        while url:
            data = await self._request("GET", url)
            pages_read += 1
            body = data.get("data", {})
            if not isinstance(body, dict):
                raise ValueError("Folk list_companies payload missing object `data`")
            raw_items = body.get("items", [])
            if isinstance(raw_items, list):
                items.extend(item for item in raw_items if isinstance(item, dict))
            pagination = body.get("pagination", {})
            url = (
                str(pagination.get("nextLink"))
                if isinstance(pagination, dict) and pagination.get("nextLink")
                else ""
            )
            if max_pages is not None and pages_read >= max_pages:
                break
        return items

    async def update_contact(
        self,
        contact_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        data = await self._request(
            "PATCH",
            f"{self._settings.folk_base_url}/v1/contacts/{contact_id}",
            json_payload=payload,
        )
        return _data_object(data)

    async def list_deals(self) -> list[dict[str, Any]]:
        path = (
            f"/v1/groups/{self._settings.folk_group_id}/"
            f"{self._settings.folk_object_type}?limit=100"
        )
        url = f"{self._settings.folk_base_url}{path}"
        items: list[dict[str, Any]] = []
        while url:
            data = await self._request("GET", url)
            body = data.get("data", {})
            if not isinstance(body, dict):
                raise ValueError("Folk list_deals payload missing object `data`")
            raw_items = body.get("items", [])
            if isinstance(raw_items, list):
                items.extend(item for item in raw_items if isinstance(item, dict))
            pagination = body.get("pagination", {})
            url = (
                str(pagination.get("nextLink"))
                if isinstance(pagination, dict) and pagination.get("nextLink")
                else ""
            )
        return items

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        last_error: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            try:
                if self._http_client is not None:
                    response = await self._http_client.request(
                        method,
                        url,
                        headers=headers,
                        json=json_payload,
                        timeout=self._settings.request_timeout_seconds,
                    )
                else:
                    async with httpx.AsyncClient(
                        timeout=self._settings.request_timeout_seconds
                    ) as client:
                        response = await client.request(
                            method,
                            url,
                            headers=headers,
                            json=json_payload,
                        )

                if (
                    _should_retry_response(response)
                    and attempt < self._settings.max_retries
                ):
                    await asyncio.sleep(_retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < self._settings.max_retries:
                    await asyncio.sleep(min(2**attempt, 8))
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Folk request failed: {method} {url}")


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return float(min(2**attempt, 8))


def _should_retry_response(response: httpx.Response) -> bool:
    return response.status_code == 429 or response.status_code >= 500


def _validate_resource_url(resource_url: str, base_url: str) -> None:
    candidate = urlparse(resource_url)
    base = urlparse(base_url)
    if candidate.scheme != base.scheme or candidate.netloc != base.netloc:
        raise ValueError("Unexpected Folk resource URL origin")


def _data_object(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("data")
    return value if isinstance(value, dict) else {}
