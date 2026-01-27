"""
Notion Feedback Module

Domain-specific functions for managing feedback tickets in Notion.
Uses generic page operations and property builders from _pages and _properties.
"""

from typing import Optional

from notion_client import AsyncClient

from utils.log import logger

from ._client import get_notion_client, get_notion_feedback_database_id
from ._pages import create_page, update_page_properties
from ._properties import (
    build_email_property,
    build_multi_select_property,
    build_paragraph_block,
    build_relation_property,
    build_rich_text_property,
    build_select_property,
    build_title_property,
    build_url_property,
)
from ._utils import format_notion_page_id

# =============================================================================
# FEEDBACK-SPECIFIC FUNCTIONS
# =============================================================================


async def get_client_page_id_by_account_name(
    account_name: str, client: Optional[AsyncClient] = None
) -> Optional[str]:
    """
    Query the Clients Master Database to find the client page ID by account_name.

    Args:
        account_name: The account name to search for
        client: Optional Notion client to reuse

    Returns:
        str: The Notion page ID of the client, or None if not found
    """
    try:
        if client is None:
            try:
                client = get_notion_client()
            except ValueError as e:
                logger.error(f"[Notion] Failed to get Notion client: {e}")
                return None

        # At this point client is guaranteed to be not None
        assert client is not None

        # Clients Master Database ID (format with dashes for API calls)
        clients_db_id = format_notion_page_id("1c58c0822e4980908856f2668ce991b4")

        # Query the database using notion_client's built-in method
        data = await client.databases.query(
            database_id=clients_db_id,
            filter={
                "property": "account_name",
                "select": {"equals": account_name},
            },
        )

        results = data.get("results", [])
        if not results:
            logger.warning(
                f"[Notion] No client found with account_name: {account_name}",
                extra={"account_name": account_name},
            )
            return None

        # Return the first matching page ID
        client_page_id = results[0].get("id")
        if client_page_id:
            # Format without dashes for consistency
            client_page_id = format_notion_page_id(client_page_id).replace("-", "")
            logger.info(
                f"[Notion] Found client page for account: {account_name}",
                extra={"account_name": account_name, "client_page_id": client_page_id},
            )
            return client_page_id

        return None

    except Exception as e:
        logger.error(
            f"[Notion] Error querying Clients Master Database: {e}",
            extra={"account_name": account_name},
            exc_info=True,
        )
        return None


async def create_feedback_ticket(
    client_name: str,
    user_name: Optional[str],
    feedback_text: Optional[str],
    conversation_link: Optional[str],
    conversation_id: str,
    tags: Optional[list[str]] = None,
    reaction: Optional[str] = None,
    user_email: Optional[str] = None,
    client: Optional[AsyncClient] = None,
) -> Optional[str]:
    """
    Create a feedback ticket in Notion (convenience wrapper).

    This is a domain-specific helper that uses the generic create_page() function.
    For other use cases, use create_page() directly with your own properties.

    Args:
        client_name: Name of the client/account
        user_name: Name of the user who submitted feedback
        feedback_text: The main feedback content
        conversation_link: Optional URL to the conversation
        conversation_id: ID of the conversation
        tags: List of feedback tags (optional)
        reaction: Feedback reaction (thumbs_up/thumbs_down) (optional)
        user_email: Email of the user (optional)
        client: Optional Notion client to reuse

    Returns:
        str: URL of the created Notion page, or None if creation failed
    """
    try:
        database_id = get_notion_feedback_database_id()
    except ValueError as e:
        logger.error(f"[Notion] Failed to get feedback database ID: {e}")
        return None

    # Query Clients Master Database to get client page ID for relation
    client_page_id = await get_client_page_id_by_account_name(client_name, client)
    if not client_page_id:
        logger.warning(
            f"[Notion] Could not find client page for account: {client_name}. "
            "Ticket will be created without Client relation.",
            extra={"account_name": client_name},
        )

    # Build title with optional reaction emoji
    title = f"Feedback: {client_name}"
    if reaction:
        emoji = (
            "👍"
            if reaction == "thumbs_up"
            else "👎" if reaction == "thumbs_down" else ""
        )
        if emoji:
            title = f"{emoji} {title}"

    # Build properties using helper functions
    properties = {
        "Name": build_title_property(title),
        "Status": build_select_property("New"),
        "User Name": build_rich_text_property(user_name or user_email or "Unknown"),
        "Feedback": build_rich_text_property(
            feedback_text or "(No feedback text provided)"
        ),
        "Conversation ID": build_rich_text_property(conversation_id),
    }

    # Add Client relation if we found the client page
    if client_page_id:
        properties["Client"] = build_relation_property([client_page_id])

    # Add optional properties
    if tags:
        properties["Tags"] = build_multi_select_property(tags)
    if user_email:
        properties["User Email"] = build_email_property(user_email)
    if conversation_link:
        properties["Conversation Link"] = build_url_property(conversation_link)
    if reaction:
        properties["Reaction"] = build_select_property(reaction)

    # Build page content (children blocks)
    children = [build_paragraph_block(feedback_text or "(No feedback text provided)")]

    # Use generic create_page function
    page_url = await create_page(
        database_id=database_id,
        properties=properties,
        children=children,
        client=client,
    )

    if page_url:
        logger.info(
            "[Notion] Successfully created feedback ticket",
            extra={
                "client_name": client_name,
                "conversation_id": conversation_id,
                "notion_page_url": page_url,
            },
        )

    return page_url


async def update_feedback_status(
    notion_page_id: str,
    status: str,
    client: Optional[AsyncClient] = None,
) -> bool:
    """
    Update the status of a feedback ticket in Notion (convenience wrapper).

    This is a domain-specific helper that uses the generic update_page_properties().
    For other use cases, use update_page_properties() directly.

    Args:
        notion_page_id: The Notion page ID (32 hex characters without dashes)
        status: The new status value (e.g., "New", "Investigating", "Changes Now Live")
        client: Optional Notion client to reuse

    Returns:
        bool: True if update was successful, False otherwise
    """
    # Valid status values for feedback tickets
    valid_statuses = {
        "New",
        "Investigating",
        "Changes Now Live",
        "Out of Scope",
        "Resolved",
        "In Progress",
    }

    if status not in valid_statuses:
        logger.warning(
            f"[Notion] Invalid status value: {status}. Valid values: {', '.join(valid_statuses)}",
            extra={"notion_page_id": notion_page_id, "attempted_status": status},
        )
        return False

    properties = {"Status": build_select_property(status)}

    success = await update_page_properties(
        page_id=notion_page_id,
        properties=properties,
        client=client,
    )

    if success:
        logger.info(
            "[Notion] Successfully updated feedback ticket status",
            extra={"notion_page_id": notion_page_id, "new_status": status},
        )

    return success
