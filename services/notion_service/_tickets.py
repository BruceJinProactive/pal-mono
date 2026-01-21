"""
Notion Ticket Management Module

Provides functionality for creating feedback tickets in Notion.
"""

from typing import Optional

from notion_client import AsyncClient
from notion_client.errors import APIResponseError

from utils.log import logger

from ._client import get_notion_client, get_notion_feedback_database_id


async def create_feedback_ticket(
    client_name: str,
    user_name: Optional[str],
    feedback_text: Optional[str],
    conversation_link: str,
    conversation_id: str,
    tags: Optional[list[str]] = None,
    reaction: Optional[str] = None,
    user_email: Optional[str] = None,
    client: Optional[AsyncClient] = None,
) -> Optional[str]:
    """
    Create a feedback ticket in Notion.

    This function creates a new page in the configured Notion Feedback Inbox database
    with all feedback details. It automatically assigns an FDE based on the client name.

    Args:
        client_name: Name of the client/account
        user_name: Name of the user who submitted feedback
        feedback_text: The main feedback content
        conversation_link: URL to the conversation
        conversation_id: ID of the conversation
        tags: List of feedback tags (optional)
        reaction: Feedback reaction (thumbs_up/thumbs_down) (optional)
        user_email: Email of the user (optional)
        client: Optional Notion client to reuse (creates new one if not provided)

    Returns:
        str: URL of the created Notion page, or None if creation failed

    Note:
        - Uses NOTION_API_KEY from environment/secrets for authentication
        - Uses NOTION_FEEDBACK_DB_ID from environment for the target database
        - Feedback tickets go into a separate 'Feedback Inbox' database
        - Failures are logged but do not raise exceptions
    """
    try:
        # Get Notion client and database ID
        if client is None:
            try:
                client = get_notion_client()
            except ValueError as e:
                logger.error(f"[Notion] Failed to get Notion client: {e}")
                return None

        try:
            database_id = get_notion_feedback_database_id()
        except ValueError as e:
            logger.error(f"[Notion] Failed to get feedback database ID: {e}")
            return None

        # Build the title (Name field)
        title = f"Feedback: {client_name}"
        if reaction:
            emoji = (
                "👍"
                if reaction == "thumbs_up"
                else "👎" if reaction == "thumbs_down" else ""
            )
            if emoji:
                title = f"{emoji} {title}"

        # Build properties for the Notion Feedback Inbox page
        # Required fields: Client Name, User Name, Feedback, Tags, Phone, Status
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "Status": {"select": {"name": "New"}},
            "Client": {"select": {"name": client_name}},
        }

        # User Name field (required in feedback inbox)
        user_value = user_name or user_email or "Unknown"
        properties["User Name"] = {"rich_text": [{"text": {"content": user_value}}]}

        # Feedback field (the main feedback text)
        if feedback_text:
            feedback_value = feedback_text
        else:
            feedback_value = "(No feedback text provided)"
        properties["Feedback"] = {"rich_text": [{"text": {"content": feedback_value}}]}

        # Tags field (multi-select)
        if tags:
            properties["Tags"] = {"multi_select": [{"name": tag} for tag in tags]}

        # Optional: Add user email (not in required fields, but useful)
        if user_email:
            properties["User Email"] = {"email": user_email}

        # Optional: Add conversation link
        if conversation_link:
            properties["Conversation Link"] = {"url": conversation_link}

        # Optional: Add reaction
        if reaction:
            properties["Reaction"] = {"select": {"name": reaction}}

        # Optional: Add conversation ID
        properties["Conversation ID"] = {
            "rich_text": [{"text": {"content": conversation_id}}]
        }

        # Build the page content (children blocks)
        children = []

        # Add feedback text as a paragraph block if provided
        if feedback_text:
            children.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": feedback_text},
                            }
                        ]
                    },
                }
            )
        else:
            # Add placeholder if no feedback text
            children.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": "(No feedback text provided)"},
                            }
                        ]
                    },
                }
            )

        # Create the page in Notion
        response = await client.pages.create(
            parent={"database_id": database_id},
            properties=properties,
            children=children,
        )

        # Extract the page URL
        page_url = response.get("url")

        logger.info(
            "[Notion] Successfully created feedback ticket",
            extra={
                "client_name": client_name,
                "conversation_id": conversation_id,
                "notion_page_url": page_url,
                "assigned_fde": "",
            },
        )

        return page_url

    except APIResponseError as e:
        logger.error(
            f"[Notion] API error creating ticket: {e.code} - {e}",
            extra={
                "client_name": client_name,
                "conversation_id": conversation_id,
                "error_details": str(e),
            },
        )
        return None
    except Exception as e:
        logger.error(
            f"[Notion] Unexpected error creating ticket: {e}",
            extra={
                "client_name": client_name,
                "conversation_id": conversation_id,
            },
        )
        return None


async def update_feedback_status(
    notion_page_id: str,
    status: str,
    client: Optional[AsyncClient] = None,
) -> bool:
    """
    Update the status of a feedback ticket in Notion.

    This syncs status from Slack (source of truth) to Notion.

    Args:
        notion_page_id: The Notion page ID (32 hex characters without dashes)
        status: The new status value (e.g., "New", "Investigating", "Changes Now Live")
        client: Optional Notion client to reuse (creates new one if not provided)

    Returns:
        bool: True if update was successful, False otherwise

    Note:
        - Slack is the source of truth; this function syncs state to Notion
        - Uses NOTION_API_KEY from environment/secrets for authentication
        - Failures are logged but do not raise exceptions
        - Status must match an existing option in your Notion database's Status field
    """
    try:
        # Get Notion client
        if client is None:
            try:
                client = get_notion_client()
            except ValueError as e:
                logger.error(f"[Notion] Failed to get Notion client: {e}")
                return False

        # Format the page ID correctly (Notion expects UUID format with dashes)
        # Input is 32 hex chars without dashes, need to add dashes in format: 8-4-4-4-12
        if len(notion_page_id) == 32 and "-" not in notion_page_id:
            formatted_page_id = (
                f"{notion_page_id[:8]}-{notion_page_id[8:12]}-"
                f"{notion_page_id[12:16]}-{notion_page_id[16:20]}-{notion_page_id[20:]}"
            )
        else:
            formatted_page_id = notion_page_id

        # Update the page properties
        await client.pages.update(
            page_id=formatted_page_id,
            properties={
                "Status": {"select": {"name": status}},
            },
        )

        logger.info(
            "[Notion] Successfully updated feedback ticket status from Slack",
            extra={
                "notion_page_id": notion_page_id,
                "new_status": status,
            },
        )
        return True

    except APIResponseError as e:
        logger.error(
            f"[Notion] API error updating ticket status: {e.code} - {e}",
            extra={
                "notion_page_id": notion_page_id,
                "status": status,
                "error_details": str(e),
            },
        )
        return False
    except Exception as e:
        logger.error(
            f"[Notion] Unexpected error updating ticket status: {e}",
            extra={
                "notion_page_id": notion_page_id,
                "status": status,
            },
        )
        return False
