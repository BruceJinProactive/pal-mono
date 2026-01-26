"""
Notion Pages Module

Generic Notion page operations for creating and updating pages in any database.
These functions are framework-agnostic and can be used for any Notion use case.
"""

from typing import Any, Dict, List, Optional

from notion_client import AsyncClient
from notion_client.errors import APIResponseError

from utils.log import logger

from ._client import get_notion_client
from ._utils import format_notion_page_id


async def create_page(
    database_id: str,
    properties: Dict[str, Any],
    children: Optional[List[Dict[str, Any]]] = None,
    client: Optional[AsyncClient] = None,
) -> Optional[str]:
    """
    Create a new page in any Notion database.

    Args:
        database_id: The Notion database ID
        properties: Page properties as a dictionary (Notion API format)
        children: Optional list of block children (page content)
        client: Optional Notion client to reuse

    Returns:
        str: URL of the created page, or None if creation failed

    """
    try:
        if client is None:
            try:
                client = get_notion_client()
            except ValueError as e:
                logger.error(f"[Notion] Failed to get Notion client: {e}")
                return None

        response = await client.pages.create(
            parent={"database_id": database_id},
            properties=properties,
            children=children or [],
        )

        page_url = response.get("url")
        logger.info(
            "[Notion] Successfully created page",
            extra={"database_id": database_id, "page_url": page_url},
        )
        return page_url

    except APIResponseError as e:
        logger.error(
            f"[Notion] API error creating page: {e.code} - {e}",
            extra={"database_id": database_id, "error_details": str(e)},
        )
        return None
    except Exception as e:
        logger.error(
            f"[Notion] Unexpected error creating page: {e}",
            extra={"database_id": database_id},
        )
        return None


async def update_page_properties(
    page_id: str,
    properties: Dict[str, Any],
    client: Optional[AsyncClient] = None,
) -> bool:
    """
    Update properties of any Notion page.

    Args:
        page_id: The Notion page ID (32 hex characters, with or without dashes)
        properties: Properties to update (Notion API format)
        client: Optional Notion client to reuse

    Returns:
        bool: True if successful, False otherwise

    """
    try:
        if client is None:
            try:
                client = get_notion_client()
            except ValueError as e:
                logger.error(f"[Notion] Failed to get Notion client: {e}")
                return False

        formatted_page_id = format_notion_page_id(page_id)

        # IMPORTANT: archived=False ensures the page is NOT archived during update
        response = await client.pages.update(
            page_id=formatted_page_id,
            properties=properties,
            archived=False,
        )

        logger.info(
            "[Notion] Successfully updated page properties",
            extra={
                "page_id": page_id,
                "formatted_page_id": formatted_page_id,
                "properties": list(properties.keys()),
                "properties_count": len(properties),
                "response_url": response.get("url"),
                "response_archived": response.get("archived", False),
            },
        )
        return True

    except APIResponseError as e:
        logger.error(
            f"[Notion] API error updating page: {e.code} - {e}",
            extra={"page_id": page_id, "error_details": str(e)},
        )
        return False
    except Exception as e:
        logger.error(
            f"[Notion] Unexpected error updating page: {e}",
            extra={"page_id": page_id},
        )
        return False
