"""
Internal Tools Module

Functions for querying the Internal Tools Notion database and submitting
tool feedback to the Internal Tools Feedback database.
"""

from typing import Any, Optional

from notion_client import AsyncClient

from utils.log import logger
from utils.secret import get_server_secret_with_fallback

from ._client import get_notion_client
from ._pages import create_page
from ._properties import (
    build_people_property,
    build_relation_property,
    build_rich_text_property,
    build_select_property,
    build_status_property,
    build_title_property,
)
from ._utils import format_notion_page_id

# Notion API limits rich text content to 2000 characters
_NOTION_TEXT_LIMIT = 2000


def _get_database_id(key: str, fallback: str) -> str:
    """Get a Notion database ID from secrets/env, falling back to a default."""
    try:
        value = get_server_secret_with_fallback(key)
        return value or fallback
    except (ValueError, Exception):
        return fallback


# Notion Database IDs — loaded from env/secrets per environment
INTERNAL_TOOLS_DATABASE_ID = _get_database_id(
    "NOTION_INTERNAL_TOOLS_DB_ID", "ac0205ecad4345bea1ffd1203800bf6f"
)
TOOL_FEEDBACK_DATABASE_ID = _get_database_id(
    "NOTION_TOOL_FEEDBACK_DB_ID", "3188c0822e4980ba8e45d6be09e00d7f"
)
TOOL_REQUESTS_DATABASE_ID = _get_database_id(
    "NOTION_TOOL_REQUESTS_DB_ID", "31b8c0822e4980cbb792fb41ca99bd7f"
)


async def find_notion_user_id_by_name(
    name: str,
    client: Optional[AsyncClient] = None,
) -> Optional[str]:
    """Look up a Notion workspace user ID by display name (case-insensitive).

    Args:
        name: Display name to search for (e.g. Slack username)
        client: Optional Notion client to reuse

    Returns:
        The Notion user ID if a match is found, None otherwise.
    """
    try:
        if client is None:
            try:
                client = get_notion_client()
            except ValueError:
                return None

        # Normalize: "jane.doe" -> "jane doe" for matching against
        # Notion display names like "Jane Doe"
        name_normalized = name.lower().replace(".", " ").replace("_", " ")
        cursor: Optional[str] = None
        total_checked = 0
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            resp = await client.users.list(**params)
            for user in resp.get("results", []):
                total_checked += 1
                if user.get("name", "").lower() == name_normalized:
                    logger.info(
                        "[Notion] Found user matching '%s' -> %s",
                        name,
                        user.get("id"),
                    )
                    return user["id"]
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")

        logger.info(
            "[Notion] No user found matching name '%s' (checked %d users)",
            name,
            total_checked,
        )
        return None
    except Exception as e:
        logger.warning("[Notion] Failed to look up user by name: %s", e)
        return None


async def get_internal_tools(
    client: Optional[AsyncClient] = None,
) -> list[dict]:
    """
    Query the Internal Tools Notion database to get all tool names and page IDs.

    Returns:
        list[dict]: List of tools with 'name' and 'page_id' fields, sorted alphabetically.
            Only includes tools with Status=Live.
    """
    try:
        if client is None:
            try:
                client = get_notion_client()
            except ValueError as e:
                logger.error(
                    f"[Notion] Failed to get Notion client for internal tools: {e}"
                )
                return []

        all_tools: list[dict] = []
        has_more = True
        start_cursor: str | None = None

        while has_more:
            query_params: dict = {
                "database_id": INTERNAL_TOOLS_DATABASE_ID,
                "filter": {
                    "property": "Status",
                    "select": {"equals": "Live"},
                },
                "page_size": 100,
            }
            if start_cursor:
                query_params["start_cursor"] = start_cursor

            data = await client.databases.query(**query_params)
            results = data.get("results", [])

            for page in results:
                props = page.get("properties", {})
                # Extract the title property (Name)
                name = None
                name_prop = props.get("Name", {})
                if name_prop.get("type") == "title":
                    title_parts = name_prop.get("title", [])
                    name = "".join(part.get("plain_text", "") for part in title_parts)

                if name and name.strip():
                    page_id = page.get("id", "")

                    # Extract the Owner people property (first owner)
                    owner_id = ""
                    owner_prop = props.get("Owner", {})
                    if owner_prop.get("type") == "people":
                        people = owner_prop.get("people", [])
                        if people:
                            owner_id = people[0].get("id", "")

                    all_tools.append(
                        {
                            "name": name.strip(),
                            "page_id": page_id,
                            "owner_id": owner_id,
                        }
                    )

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        all_tools.sort(key=lambda t: t["name"])

        logger.info(
            f"[Notion] Found {len(all_tools)} internal tools",
            extra={"tool_count": len(all_tools)},
        )

        return all_tools

    except Exception as e:
        logger.error(
            f"[Notion] Failed to query internal tools: {e}",
            exc_info=True,
        )
        return []


async def submit_tool_feedback(
    tool_name: str,
    tool_page_id: str,
    request_type: str,
    priority: str,
    feedback_text: str,
    submitted_by: str,
    submitted_by_id: str = "",
    tool_owner_id: str = "",
    client: Optional[AsyncClient] = None,
) -> Optional[str]:
    """
    Submit feedback for an internal tool to the Notion feedback database.

    Args:
        tool_name: Display name of the internal tool (for logging)
        tool_page_id: Notion page ID of the tool (for relation property)
        request_type: Type of feedback (Bug, Improvement, Feature request, etc.)
        priority: Priority level (P0, P1, P2, P3)
        feedback_text: The feedback content
        submitted_by: Slack username of the person submitting
        submitted_by_id: Slack user ID of the submitter
        tool_owner_id: Notion user ID of the tool owner (for Assigned To)
        client: Optional Notion client to reuse

    Returns:
        str: URL of the created Notion page, or None if creation failed
    """
    try:
        # Format tool page ID with dashes for the Notion API
        formatted_tool_id = format_notion_page_id(tool_page_id)

        properties: dict[str, Any] = {
            "Feedback": build_title_property(feedback_text[:_NOTION_TEXT_LIMIT]),
            "Tool": build_relation_property([formatted_tool_id]),
            "Request type": build_select_property(request_type),
            "Priority": build_select_property(priority),
            "Status": build_status_property("New"),
        }

        # Try to resolve the Slack user name to a Notion user for the Requester field
        notion_user_id = await find_notion_user_id_by_name(submitted_by, client=client)
        if notion_user_id:
            properties["Requester"] = build_people_property([notion_user_id])

        # Auto-assign to the tool owner if available
        if tool_owner_id:
            properties["Assigned To"] = build_people_property([tool_owner_id])

        page_url = await create_page(
            database_id=TOOL_FEEDBACK_DATABASE_ID,
            properties=properties,
            client=client,
        )

        if page_url:
            logger.info(
                "[Notion] Successfully submitted tool feedback",
                extra={
                    "tool_name": tool_name,
                    "request_type": request_type,
                    "priority": priority,
                    "submitted_by": submitted_by,
                    "notion_page_url": page_url,
                },
            )

        return page_url

    except Exception as e:
        logger.error(
            f"[Notion] Failed to submit tool feedback: {e}",
            extra={
                "tool_name": tool_name,
                "request_type": request_type,
            },
            exc_info=True,
        )
        return None


async def submit_tool_request(
    request_title: str,
    priority: str,
    problem_context: str = "",
    proposed_solution: str = "",
    submitted_by: str = "",
    submitted_by_id: str = "",
    client: Optional[AsyncClient] = None,
) -> Optional[str]:
    """
    Submit a new internal tool request to the Notion tool requests database.

    Args:
        request_title: Short description of the requested tool
        priority: Priority level (P0, P1, P2, P3)
        problem_context: Background and problem statement (optional)
        proposed_solution: Suggested approach or solution (optional)
        submitted_by: Slack username of the person submitting
        submitted_by_id: Slack user ID of the submitter
        client: Optional Notion client to reuse

    Returns:
        str: URL of the created Notion page, or None if creation failed
    """
    try:
        properties: dict[str, Any] = {
            "Request": build_title_property(request_title[:_NOTION_TEXT_LIMIT]),
            "Priority": build_select_property(priority),
            "Status": build_status_property("New"),
        }

        if problem_context.strip():
            properties["Problem / context"] = build_rich_text_property(
                problem_context[:_NOTION_TEXT_LIMIT]
            )
        if proposed_solution.strip():
            properties["Proposed solution"] = build_rich_text_property(
                proposed_solution[:_NOTION_TEXT_LIMIT]
            )

        if submitted_by:
            notion_user_id = await find_notion_user_id_by_name(
                submitted_by, client=client
            )
            if notion_user_id:
                properties["Requester"] = build_people_property([notion_user_id])

        page_url = await create_page(
            database_id=TOOL_REQUESTS_DATABASE_ID,
            properties=properties,
            client=client,
        )

        if page_url:
            logger.info(
                "[Notion] Successfully submitted tool request",
                extra={
                    "request_title": request_title,
                    "priority": priority,
                    "submitted_by": submitted_by,
                    "notion_page_url": page_url,
                },
            )

        return page_url

    except Exception as e:
        logger.error(
            f"[Notion] Failed to submit tool request: {e}",
            extra={"request_title": request_title},
            exc_info=True,
        )
        return None
