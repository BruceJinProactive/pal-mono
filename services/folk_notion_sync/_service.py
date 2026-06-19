from __future__ import annotations

import asyncio
from threading import Lock
from typing import Any, Protocol

from services.folk_notion_sync._mapping import (
    CompanyProjection,
    build_notion_properties,
    project_company_sync,
)
from services.folk_notion_sync._settings import (
    FolkNotionSyncSettings,
    get_folk_notion_sync_settings,
)
from services.folk_notion_sync._webhook import FolkWebhookEvent
from utils.log import logger

SUPPORTED_WRITE_EVENTS = {"object.created", "object.updated"}
_company_locks: dict[str, asyncio.Lock] = {}
_company_locks_guard = Lock()


class FolkSyncClient(Protocol):
    async def get_resource_url(self, resource_url: str) -> dict[str, Any]: ...

    async def get_company(self, company_id: str) -> dict[str, Any]: ...

    async def list_deals(self) -> list[dict[str, Any]]: ...


class NotionSyncClient(Protocol):
    async def find_page(self, company: CompanyProjection) -> dict[str, Any] | None: ...

    async def create_page(
        self,
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...

    async def update_page(
        self,
        page_id: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]: ...


async def process_folk_event(
    event: FolkWebhookEvent,
    *,
    settings: FolkNotionSyncSettings | None = None,
    folk_client: FolkSyncClient | None = None,
    notion_client: NotionSyncClient | None = None,
) -> None:
    resolved_settings = settings or get_folk_notion_sync_settings()
    if not resolved_settings.enabled:
        logger.info(
            "[FolkNotionSync] Ignoring event because sync is disabled",
            extra={"event_id": event.id, "event_type": event.type},
        )
        return

    if event.type == "object.deleted":
        logger.info(
            "[FolkNotionSync] Ignoring deleted Folk deal",
            extra={"event_id": event.id, "resource_id": event.resource_id},
        )
        return

    if event.type not in SUPPORTED_WRITE_EVENTS:
        logger.info(
            "[FolkNotionSync] Ignoring unsupported Folk event",
            extra={"event_id": event.id, "event_type": event.type},
        )
        return

    try:
        if folk_client is None:
            from services.folk_notion_sync._folk import FolkClient

            folk = FolkClient(resolved_settings)
        else:
            folk = folk_client
        if notion_client is None:
            from services.folk_notion_sync._notion import NotionDataSourceClient

            notion = NotionDataSourceClient(resolved_settings)
        else:
            notion = notion_client
        raw_deal = await folk.get_resource_url(event.resource_url)
        target_deal = _data_object(raw_deal)
        if not target_deal:
            raise ValueError(f"Folk deal payload was empty for {event.resource_id}")

        company_id = _first_company_id(target_deal)
        company = await folk.get_company(company_id) if company_id else {}
        all_deals = await folk.list_deals()
        projection = project_company_sync(
            target_deal,
            all_deals,
            company,
            resolved_settings.folk_group_id,
        )
        company_lock = _company_lock(projection)
        async with company_lock:
            page = await notion.find_page(projection)
            if page:
                await notion.update_page(
                    str(page["id"]),
                    build_notion_properties(
                        projection,
                        source="webhook",
                        include_title=False,
                    ),
                )
                action = "updated"
            else:
                await notion.create_page(
                    build_notion_properties(
                        projection,
                        source="webhook",
                        include_title=True,
                    ),
                    children=_build_page_children(projection),
                )
                action = "created"

        logger.info(
            "[FolkNotionSync] Synced Folk deal to Notion",
            extra={
                "event_id": event.id,
                "event_type": event.type,
                "resource_id": event.resource_id,
                "company_id": projection.company_id,
                "company_name": projection.name,
                "action": action,
            },
        )
    except Exception as exc:
        from services.folk_notion_sync._alerts import send_sync_failure_alert

        logger.exception(
            "[FolkNotionSync] Failed to sync Folk event",
            extra={"event_id": event.id, "event_type": event.type},
        )
        await send_sync_failure_alert(
            resolved_settings,
            title=f"{event.type} for {event.resource_id}",
            detail=str(exc),
            event_id=event.id,
            event_type=event.type,
        )


def _data_object(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("data")
    return value if isinstance(value, dict) else {}


def _first_company_id(deal: dict[str, Any]) -> str:
    value = deal.get("companies")
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return str(value[0].get("id") or "")
    value = deal.get("company")
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return ""


def _company_lock(company: CompanyProjection) -> asyncio.Lock:
    key = company.company_id or company.key or company.name
    with _company_locks_guard:
        lock = _company_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _company_locks[key] = lock
        return lock


def _build_page_children(company: CompanyProjection) -> list[dict[str, Any]]:
    summary = "\n".join(f"- {deal.name} ({deal.id})" for deal in company.deals)
    return [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Folk sync"}}]
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": (
                                "Created from Folk Pipeline Review. Deal-level and "
                                "company-level fields are synced into properties."
                            )
                        },
                    }
                ]
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": summary[:2000]}}]
            },
        },
    ]
