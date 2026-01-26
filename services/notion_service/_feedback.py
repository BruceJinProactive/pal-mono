"""
Notion Feedback Module

Domain-specific functions for managing feedback tickets in Notion.
Uses generic page operations and property builders from _pages and _properties.
"""

from typing import Optional

from notion_client import AsyncClient

from utils.log import logger

from ._client import get_notion_feedback_database_id
from ._pages import create_page, update_page_properties
from ._properties import (
    build_email_property,
    build_multi_select_property,
    build_paragraph_block,
    build_rich_text_property,
    build_select_property,
    build_title_property,
    build_url_property,
)

# =============================================================================
# FEEDBACK-SPECIFIC FUNCTIONS
# =============================================================================


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
        "Client": build_select_property(client_name),
        "User Name": build_rich_text_property(user_name or user_email or "Unknown"),
        "Feedback": build_rich_text_property(
            feedback_text or "(No feedback text provided)"
        ),
        "Conversation ID": build_rich_text_property(conversation_id),
    }

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
