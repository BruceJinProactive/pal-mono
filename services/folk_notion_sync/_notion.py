from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from services.folk_notion_sync._mapping import CompanyProjection, normalize_name
from services.folk_notion_sync._settings import FolkNotionSyncSettings
from utils.secret import get_client_secret_with_fallback


class NotionDataSourceClient:
    def __init__(
        self,
        settings: FolkNotionSyncSettings,
        *,
        api_key: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._api_key = api_key or get_client_secret_with_fallback("NOTION_API_KEY")
        self._http_client = http_client

    async def find_page(self, company: CompanyProjection) -> dict[str, Any] | None:
        pages = await self.query_pages()
        by_company_id: list[dict[str, Any]] = []
        by_deal_id: list[dict[str, Any]] = []
        by_name: list[dict[str, Any]] = []
        deal_ids = {deal.id for deal in company.deals if deal.id}
        company_key = normalize_name(company.name)

        for page in pages:
            properties = _properties(page)
            company_ids = _id_tokens(_plain_text(properties.get("Folk Company IDs")))
            deal_ids_text = _id_tokens(_plain_text(properties.get("Folk Deal IDs")))
            page_name = _plain_text(properties.get("Name"))
            account_name = _select_name(properties.get("account_name"))
            if company.company_id and company.company_id in company_ids:
                by_company_id.append(page)
            elif deal_ids and any(deal_id in deal_ids_text for deal_id in deal_ids):
                by_deal_id.append(page)
            elif company_key and company_key in {
                normalize_name(page_name),
                normalize_name(account_name),
            }:
                by_name.append(page)

        for candidates in (by_company_id, by_deal_id, by_name):
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                raise ValueError(
                    f"Multiple Notion pages matched Folk company {company.name}"
                )
        return None

    async def query_pages(self) -> list[dict[str, Any]]:
        path = f"/v1/data_sources/{self._settings.notion_data_source_id}/query"
        body: dict[str, Any] = {"page_size": 100}
        pages: list[dict[str, Any]] = []
        while True:
            data = await self._request("POST", path, body)
            results = data.get("results", [])
            if isinstance(results, list):
                pages.extend(item for item in results if isinstance(item, dict))
            if not data.get("has_more"):
                break
            body["start_cursor"] = data.get("next_cursor")
        return pages

    async def create_page(
        self,
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/pages",
            {
                "parent": {"data_source_id": self._settings.notion_data_source_id},
                "properties": properties,
                "children": children or [],
            },
        )

    async def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "PATCH",
            f"/v1/pages/{page_id}",
            {"properties": properties},
        )

    async def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._settings.notion_base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Notion-Version": self._settings.notion_version,
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            try:
                if self._http_client is not None:
                    response = await self._http_client.request(
                        method,
                        url,
                        headers=headers,
                        json=body,
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
                            json=body,
                        )
                if (
                    _should_retry_response(response)
                    and attempt < self._settings.max_retries
                ):
                    await asyncio.sleep(_retry_delay(response, attempt))
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise ValueError(
                        "Notion request failed "
                        f"{method} {path}: {response.status_code} "
                        f"{response.text[:2000]}"
                    ) from exc
                return response.json()
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < self._settings.max_retries:
                    await asyncio.sleep(min(2**attempt, 8))
                    continue
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Notion request failed: {method} {path}")


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


def _properties(page: dict[str, Any]) -> dict[str, Any]:
    value = page.get("properties")
    return value if isinstance(value, dict) else {}


def _plain_text(property_value: Any) -> str:
    if not isinstance(property_value, dict):
        return ""
    parts = property_value.get("rich_text") or property_value.get("title") or []
    if not isinstance(parts, list):
        return ""
    return "".join(
        str(part.get("plain_text") or "") for part in parts if isinstance(part, dict)
    )


def _id_tokens(raw: str) -> set[str]:
    return {token.strip() for token in re.split(r"[,\n;]+", raw) if token.strip()}


def _select_name(property_value: Any) -> str:
    if not isinstance(property_value, dict):
        return ""
    select = property_value.get("select")
    if isinstance(select, dict):
        return str(select.get("name") or "")
    return ""
