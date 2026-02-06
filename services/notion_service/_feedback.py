"""
Notion Feedback Module

Domain-specific functions for managing feedback tickets in Notion.
Uses generic page operations and property builders from _pages and _properties.
"""

from typing import Optional

from notion_client import AsyncClient

from utils.log import logger

from ._client import get_notion_client
from ._pages import (
    create_page,
    get_client_page_id_by_account_name,
    update_page_properties,
)
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
# CONSTANTS
# =============================================================================

# Notion feedback ticket statuses that indicate resolution
RESOLVED_STATUSES = {"Changes Now Live", "Resolved", "Out of Scope"}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _parse_ticket_properties(ticket: dict) -> dict | None:
    """
    Extract ticket properties from a Notion page object.

    Args:
        ticket: Notion page object from database query

    Returns:
        dict with parsed ticket data, or None if conversation_id is missing.
        Fields: conversation_id, status, page_id, feedback_text, user_name,
                user_email, tags, reaction, created_time
    """
    props = ticket.get("properties", {}) or {}

    # Get status
    status_prop = props.get("Status", {})
    status = None
    if status_prop.get("type") == "select":
        status_select = status_prop.get("select")
        if status_select:
            status = status_select.get("name")

    # Get conversation ID
    conv_id_prop = props.get("Conversation ID", {})
    conversation_id = None
    if conv_id_prop.get("type") == "rich_text":
        conv_id_parts = conv_id_prop.get("rich_text", [])
        conversation_id = "".join(part.get("plain_text", "") for part in conv_id_parts)

    # Skip if no conversation ID
    if not conversation_id:
        return None

    # Get feedback text
    feedback_prop = props.get("Feedback", {})
    feedback_text = None
    if feedback_prop.get("type") == "rich_text":
        feedback_parts = feedback_prop.get("rich_text", [])
        feedback_text = "".join(part.get("plain_text", "") for part in feedback_parts)

    # Get user name
    user_name_prop = props.get("User Name", {})
    user_name = None
    if user_name_prop.get("type") == "rich_text":
        user_name_parts = user_name_prop.get("rich_text", [])
        user_name = "".join(part.get("plain_text", "") for part in user_name_parts)

    # Get user email
    user_email_prop = props.get("User Email", {})
    user_email = None
    if user_email_prop.get("type") == "email":
        user_email = user_email_prop.get("email")

    # Get tags
    tags_prop = props.get("Tags", {})
    tags = []
    if tags_prop.get("type") == "multi_select":
        tag_items = tags_prop.get("multi_select", [])
        tags = [tag.get("name") for tag in tag_items if tag.get("name")]

    # Get reaction
    reaction_prop = props.get("Reaction", {})
    reaction = None
    if reaction_prop.get("type") == "select":
        reaction_select = reaction_prop.get("select")
        if reaction_select:
            reaction = reaction_select.get("name")

    # Get created time
    created_time = ticket.get("created_time")

    return {
        "conversation_id": conversation_id,
        "status": status,
        "page_id": ticket.get("id"),
        "feedback_text": feedback_text,
        "user_name": user_name,
        "user_email": user_email,
        "tags": tags,
        "reaction": reaction,
        "created_time": created_time,
    }


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
    feedback_database_id = "2f48c0822e498004a390e305518953a5"

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
        "account_name": build_select_property(
            client_name.lower()
        ),  # Normalized for fast querying
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
        database_id=feedback_database_id,
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


async def get_feedback_fde(
    client_name: str, client: Optional[AsyncClient] = None
) -> Optional[str]:
    """
    Get the FDE assigned to a client by reading the `FDE` person property
    directly from the client page in the Clients Master Database.

    Args:
        client_name: The Pal client/account name.
        client: Optional Notion AsyncClient. If not provided, a shared client
            will be created via get_notion_client().

    Returns:
        str: The FDE's name or email, or None if not found.
    """
    try:
        # Ensure we have a Notion client
        if client is None:
            try:
                client = get_notion_client()
            except ValueError as e:
                logger.error(
                    f"[Notion] Failed to get Notion client for FDE lookup: {e}",
                    extra={"client_name": client_name},
                )
                return None

        # Look up the client page in the Clients Master Database
        client_page_id = await get_client_page_id_by_account_name(
            client_name, client=client
        )
        if not client_page_id:
            logger.warning(
                "[Notion] No client page found when resolving FDE",
                extra={"client_name": client_name},
            )
            return None

        # Retrieve the client page with properties
        formatted_client_page_id = format_notion_page_id(client_page_id)
        page = await client.pages.retrieve(formatted_client_page_id)

        # Read the `FDE` person property directly
        props = page.get("properties", {}) or {}
        fde_prop = props.get("FDE")
        if not isinstance(fde_prop, dict) or fde_prop.get("type") != "people":
            logger.warning(
                "[Notion] 'FDE' property missing or not a people property on client page",
                extra={
                    "client_name": client_name,
                    "client_page_id": client_page_id,
                    "fde_prop_type": (
                        fde_prop.get("type") if isinstance(fde_prop, dict) else None
                    ),
                },
            )
            return None

        people_list = fde_prop.get("people", []) or []
        if not people_list:
            return None

        # Notion config limits this to 1 person; take the first
        first_person = people_list[0]
        if not isinstance(first_person, dict):
            return None

        name = first_person.get("name") or first_person.get("email")
        return name or None

    except Exception as e:
        logger.error(
            f"[Notion] Failed to retrieve FDE for ticket: {str(e)}",
            extra={"client_name": client_name},
            exc_info=True,
        )
        return None


async def get_feedback_tickets_by_client(
    client_name: str,
    client: Optional[AsyncClient] = None,
    reaction_filter: Optional[str] = None,
    exclude_resolved: bool = False,
) -> list[dict]:
    """
    Query the Feedback Inbox database for all feedback tickets for a specific client.

    Uses the account_name property for direct filtering (much faster than Client relation lookup).

    Args:
        client_name: The Pal client/account name (matches account_name property).
        client: Optional Notion AsyncClient. If not provided, a shared client
            will be created via get_notion_client().
        reaction_filter: Filter by reaction type ("thumbs_up", "thumbs_down", or None
            to include all reactions). Default: None (all reactions).
        exclude_resolved: If True, filters out tickets with status "Changes Now Live",
            "Resolved", or "Out of Scope" at query time. Default: False.

    Returns:
        list[dict]: List of feedback ticket data with fields:
            - conversation_id: str
            - status: str | None
            - page_id: str
            - feedback_text: str | None
            - user_name: str | None
            - user_email: str | None
            - tags: list[str]
            - reaction: str | None
            - created_time: str (ISO timestamp)
        Returns empty list if query fails or no tickets found.
    """
    try:
        # Ensure we have a Notion client
        if client is None:
            try:
                client = get_notion_client()
            except ValueError as e:
                logger.error(
                    f"[Notion] Failed to get Notion client for feedback query: {e}",
                    extra={"client_name": client_name},
                )
                return []

        # Feedback Inbox Database ID
        feedback_database_id = "2f48c0822e498004a390e305518953a5"

        # Query tickets directly by account_name property (fast!)
        # Normalize to lowercase for case-insensitive matching
        normalized_client_name = client_name.lower()

        # Build filters
        filters = [
            {
                "property": "account_name",
                "select": {"equals": normalized_client_name},
            }
        ]

        # Add reaction filter if specified
        if reaction_filter:
            filters.append(
                {"property": "Reaction", "select": {"equals": reaction_filter}}
            )

        # Filter out resolved statuses if requested
        if exclude_resolved:
            filters.append(
                {
                    "or": [
                        {"property": "Status", "select": {"is_empty": True}},
                        {
                            "and": [
                                {
                                    "property": "Status",
                                    "select": {"does_not_equal": status},
                                }
                                for status in RESOLVED_STATUSES
                            ]
                        },
                    ]
                }
            )

        all_tickets = []
        has_more = True
        start_cursor = None

        while has_more:
            query_params = {
                "database_id": feedback_database_id,
                "filter": {"and": filters} if len(filters) > 1 else filters[0],
                "page_size": 100,
            }
            if start_cursor:
                query_params["start_cursor"] = start_cursor

            data = await client.databases.query(**query_params)
            results = data.get("results", [])
            all_tickets.extend(results)

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        # Extract ticket data with all fields needed for Slack commands
        client_tickets = []
        for ticket in all_tickets:
            parsed_ticket = _parse_ticket_properties(ticket)
            if parsed_ticket:
                client_tickets.append(parsed_ticket)

        logger.info(
            f"[Notion] Found {len(client_tickets)} feedback tickets for client {client_name}",
            extra={
                "client_name": client_name,
                "normalized_client_name": normalized_client_name,
                "ticket_count": len(client_tickets),
                "reaction_filter": reaction_filter,
                "exclude_resolved": exclude_resolved,
                "raw_ticket_count": len(all_tickets),
            },
        )

        return client_tickets

    except Exception as e:
        logger.error(
            f"[Notion] Failed to query feedback tickets for client: {e!s}",
            extra={"client_name": client_name},
            exc_info=True,
        )
        return []


async def get_all_feedback_tickets(
    client: Optional[AsyncClient] = None,
    exclude_resolved: bool = True,
    reaction_filter: Optional[str] = "thumbs_down",
    limit: Optional[int] = None,
) -> dict[str, list[dict]]:
    """
    Query feedback tickets from Notion, grouped by account_name.

    Optimized with query-time filtering to reduce API load and memory usage.
    Designed for infrequent manual use (e.g., Slack commands, not scheduled polling).

    Args:
        client: Optional Notion AsyncClient. If not provided, a shared client
            will be created via get_notion_client().
        exclude_resolved: If True, filters out tickets with status "Changes Now Live",
            "Resolved", or "Out of Scope" at query time. Default: True.
        reaction_filter: Filter by reaction type ("thumbs_up", "thumbs_down", or None
            to include all reactions). Default: "thumbs_down".
        limit: Optional maximum number of tickets to return across all accounts.
            Useful for large databases to prevent excessive API calls. Default: None (unlimited).

    Returns:
        dict[str, list[dict]]: Dictionary mapping account_name to list of ticket dicts.
            Each ticket dict contains: conversation_id, status, page_id, feedback_text,
            user_name, user_email, tags, reaction, created_time.
        Returns empty dict if query fails or no tickets found.

    Performance Note:
        - Without filters: ~ceil(N/100) API calls for N tickets
        - With filters: Significantly reduced API calls and memory usage
        - At Notion's rate limit of 3 requests/second, 1000 tickets ≈ 3-4 seconds
    """
    try:
        # Ensure we have a Notion client
        if client is None:
            try:
                client = get_notion_client()
            except ValueError as e:
                logger.error(
                    f"[Notion] Failed to get Notion client for all feedback query: {e}",
                )
                return {}

        # Feedback Inbox Database ID
        feedback_database_id = "2f48c0822e498004a390e305518953a5"

        # Build filter for query-time optimization
        filters = []

        # Filter by reaction if specified
        if reaction_filter:
            filters.append(
                {"property": "Reaction", "select": {"equals": reaction_filter}}
            )

        # Filter out resolved statuses if requested
        if exclude_resolved:
            # Correct logic: status IS EMPTY OR (status != X AND status != Y AND status != Z)
            # This properly excludes all resolved statuses while preserving empty statuses
            filters.append(
                {
                    "or": [
                        {"property": "Status", "select": {"is_empty": True}},
                        {
                            "and": [
                                {
                                    "property": "Status",
                                    "select": {"does_not_equal": status},
                                }
                                for status in RESOLVED_STATUSES
                            ]
                        },
                    ]
                }
            )

        # Query tickets with pagination
        all_tickets = []
        has_more = True
        start_cursor = None

        while has_more:
            query_params = {
                "database_id": feedback_database_id,
                "page_size": 100,
            }

            # Add filters if any
            if filters:
                query_params["filter"] = (
                    {"and": filters} if len(filters) > 1 else filters[0]
                )

            if start_cursor:
                query_params["start_cursor"] = start_cursor

            data = await client.databases.query(**query_params)
            results = data.get("results", [])
            all_tickets.extend(results)

            # Check limit
            if limit and len(all_tickets) >= limit:
                total_fetched = len(all_tickets)
                all_tickets = all_tickets[:limit]
                logger.warning(
                    f"[Notion] Reached limit of {limit} tickets, truncating results",
                    extra={"limit": limit, "total_fetched": total_fetched},
                )
                break

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        # Group tickets by account_name
        tickets_by_account: dict[str, list[dict]] = {}

        for ticket in all_tickets:
            props = ticket.get("properties", {}) or {}

            # Get account_name
            account_name_prop = props.get("account_name", {})
            account_name = None
            if account_name_prop.get("type") == "select":
                account_name_select = account_name_prop.get("select")
                if account_name_select:
                    account_name = account_name_select.get("name")

            if not account_name:
                # Skip tickets without account_name
                continue

            # Parse ticket properties using helper
            parsed_ticket = _parse_ticket_properties(ticket)
            if parsed_ticket:
                if account_name not in tickets_by_account:
                    tickets_by_account[account_name] = []
                tickets_by_account[account_name].append(parsed_ticket)

        # Calculate total parsed tickets
        total_parsed = sum(len(tickets) for tickets in tickets_by_account.values())

        logger.info(
            f"[Notion] Found {total_parsed} total tickets across {len(tickets_by_account)} accounts",
            extra={
                "total_tickets": total_parsed,
                "accounts_count": len(tickets_by_account),
                "exclude_resolved": exclude_resolved,
                "reaction_filter": reaction_filter,
                "limit": limit,
            },
        )

        return tickets_by_account

    except Exception as e:
        logger.error(
            f"[Notion] Failed to query all feedback tickets: {e!s}",
            exc_info=True,
        )
        return {}


async def create_client_page(
    account_name: str,
    account_display_name: str,
    client: Optional[AsyncClient] = None,
) -> Optional[str]:
    """
    Create a client page in the Clients Master Database.

    Args:
        account_name: Name of the client account
        account_display_name: Display name of the client account
        client: Optional Notion client to reuse

    Returns:
        str: URL of the created Notion page, or None if creation failed
    """
    try:
        if client is None:
            try:
                client = get_notion_client()
            except ValueError as e:
                logger.error(f"[Notion] Failed to get Notion client: {e}")
                return None

        # Clients Master Database ID
        clients_db_id = format_notion_page_id("1c58c0822e4980908856f2668ce991b4")

        # Build properties - Name (title) with display name, and account_name (select) with account name
        properties = {
            "Name": build_title_property(account_display_name),
            "account_name": build_select_property(account_name),
            "FDE": {
                "people": [
                    {
                        "object": "user",
                        "id": "e21e8323-2e3c-4d61-bd2e-a2f2c0b1546f",
                    }
                ]
            },
        }

        # Use generic create_page function (no children blocks needed)
        page_url = await create_page(
            database_id=clients_db_id,
            properties=properties,
            children=None,
            client=client,
        )

        if page_url:
            logger.info(
                "[Notion] Successfully created client page",
                extra={
                    "account_name": account_name,
                    "account_display_name": account_display_name,
                    "notion_page_url": page_url,
                },
            )

        return page_url

    except Exception as e:
        logger.error(
            f"[Notion] Failed to create client page: {e}",
            extra={
                "account_name": account_name,
                "account_display_name": account_display_name,
            },
            exc_info=True,
        )
        return None
