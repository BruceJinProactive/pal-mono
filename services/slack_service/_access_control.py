"""
Slack Access Control Module

This module handles channel-based access control, account validation, and permissions.
"""

import uuid

from sqlalchemy.orm import Session

from utils.log import logger

# Internal channels that can see all account data
INTERNAL_CHANNELS = {
    "agent-performance",
    "test-channel",
    "#agent-performance",
    "#test-channel",
}


def extract_account_from_channel(channel_display_name: str) -> str | None:
    """
    Extract account name from client or palona channel names.

    For channels in format "#client-account-name" or "#palona-account-name",
    extracts "account-name".

    Args:
        channel_display_name: Channel name (e.g., "#client-acme-restaurant" or "#palona-acme")

    Returns:
        str | None: Account name if channel is a client/palona channel, None otherwise
    """
    normalized = channel_display_name.strip().lstrip("#").lower()
    for prefix in ["client-", "palona-"]:
        if normalized.startswith(prefix):
            # Extract everything after the prefix
            account_name = normalized[len(prefix) :]
            return account_name if account_name else None
    return None


def get_account_id_by_name(account_name: str, session: Session) -> uuid.UUID | None:
    """
    Look up account ID by account name from database.

    Args:
        account_name: Account name to look up
        session: Database session

    Returns:
        uuid.UUID | None: Account ID if found, None otherwise
    """
    try:
        from db.tables.accounts import Account

        # Query account by name (case-insensitive)
        account = (
            session.query(Account).filter(Account.name.ilike(account_name)).first()
        )

        if account:
            logger.info(
                f"[Slackbot] Found account '{account.name}' with ID {account.id}"
            )
            return account.id
        else:
            logger.warning(f"[Slackbot] No account found with name '{account_name}'")
            return None

    except Exception as e:
        logger.error(
            f"[Slackbot] Error looking up account by name '{account_name}': {e}"
        )
        return None


def determine_account_filter(
    channel: str,
    session: Session,
    account_name: str | None = None,
    channel_display_name: str | None = None,
) -> tuple[uuid.UUID | None, str | None]:
    """
    Determine which account(s) to show based on channel and optional account name.

    For client/palona channels (starting with "client-" or "palona-"):
    - Extracts account name from channel (e.g., #client-acme-restaurant -> acme-restaurant)
    - If user provides account name via "for", validates first 3 characters match
    - If no account name provided, auto-uses channel's account

    Priority:
    1. If in internal channel -> show all accounts (return None)
    2. If channel starts with "client-" or "palona-" -> extract account from channel name
       a. If account_name provided -> verify first 3 chars match channel account
       b. If no account_name -> auto-use channel's account
    3. Otherwise -> show all accounts (return None)

    Args:
        channel: Slack channel ID or name
        session: Database session
        account_name: Optional account name from message (e.g., "daily for acme")
        channel_display_name: Optional human-readable channel name for logging

    Returns:
        tuple[uuid.UUID | None, str | None]: (account_id, error_message)
        - (account_id, None) if successful
        - (None, None) if showing all accounts (internal channel)
        - (None, error_message) if error occurred
    """
    # Use display name for logging if available, otherwise use channel ID
    display_name = channel_display_name or channel

    # Priority 1: Check if it's an internal channel (can see all accounts)
    normalized_channel = channel.strip().lstrip("#")
    if normalized_channel in INTERNAL_CHANNELS or channel in INTERNAL_CHANNELS:
        logger.info(
            f"[Slackbot] Channel '{display_name}' is internal - showing all accounts"
        )
        return None, None

    # Priority 2: Check if channel is a client channel (starts with "client-")
    channel_account_name = extract_account_from_channel(display_name)
    if channel_account_name:
        # This is a client channel
        if not account_name:
            # No account specified - require user to specify
            error_msg = (
                f"Please specify the account name using the format: `daily for account-name`\n"
                f"This channel is for accounts starting with '{channel_account_name[:3]}'."
            )
            logger.warning(
                f"[Slackbot] Channel '{display_name}' is a client channel and no account specified - account name required"
            )
            return None, error_msg

        # User specified account name - verify first 3 chars match
        if len(account_name) < 3 or len(channel_account_name) < 3:
            error_msg = f"Account name too short for validation. Channel account: '{channel_account_name}'"
            logger.warning(f"[Slackbot] {error_msg}")
            return None, error_msg

        account_prefix = account_name[:3].lower()
        channel_prefix = channel_account_name[:3].lower()

        if account_prefix != channel_prefix:
            error_msg = (
                f"❌ Account '{account_name}' is not matched with this channel. "
                f"This channel is for accounts starting with '{channel_prefix}'."
            )
            logger.warning(f"[Slackbot] Account name mismatch: {error_msg}")
            return None, error_msg

        # First 3 chars match - proceed with user-specified account
        logger.info(
            f"[Slackbot] Account name '{account_name}' matches channel '{display_name}'"
        )

        # Look up account ID
        account_id = get_account_id_by_name(account_name, session)
        if account_id:
            return account_id, None
        else:
            error_msg = f"Cannot find account info for '{account_name}'. Please check the account name and try again."
            logger.warning(f"[Slackbot] Account '{account_name}' not found in database")
            return None, error_msg

    # Priority 3: Not internal, not client channel - check if account name provided
    if account_name:
        # Allow explicit account filtering in non-client channels
        account_id = get_account_id_by_name(account_name, session)
        if account_id:
            logger.info(
                f"[Slackbot] Using explicit account filter '{account_name}' in channel '{display_name}'"
            )
            return account_id, None
        else:
            error_msg = f"Cannot find account info for '{account_name}'. Please check the account name and try again."
            logger.warning(f"[Slackbot] Account '{account_name}' not found")
            return None, error_msg

    # Priority 4: For other channels without account name, allow showing all accounts
    logger.info(f"[Slackbot] Channel '{display_name}' - showing all accounts")
    return None, None


def get_project_display_name(
    project_name: str,
    session: Session | None = None,
    account_id: uuid.UUID | None = None,
) -> str:
    """
    Get project display_name from database using project_name and account_id.

    Uses service layer functions to query the database.

    Args:
        project_name: Project name string
        session: Database session (optional)
        account_id: Account UUID to help identify the project (optional but recommended)

    Returns:
        Project display_name if found, otherwise project_name
    """
    if not session:
        return project_name

    try:
        from services import account_service, project_service

        # If account_id provided, filter projects by account
        if account_id:
            # Get account by ID first
            account = account_service.get_account_by_id(session, account_id)
            if account:
                # Get all projects for this account
                projects = project_service.get_projects_by_account_id(
                    session, account.id
                )
                # Find the specific project by name
                for project in projects:
                    if project.name == project_name and project.display_name:
                        return project.display_name
        else:
            # No account_id provided, just search by project name
            project = project_service.get_project_by_name(session, project_name)
            if project and project.display_name:
                return project.display_name

        # Fallback to project_name if display_name not set or project not found
        return project_name

    except Exception as e:
        logger.warning(
            f"[Slackbot] Error looking up project display_name for project='{project_name}', account='{account_id}': {e}"
        )
        return project_name


def get_account_integrations(
    account_id: uuid.UUID, session: Session | None = None
) -> list[str]:
    """
    Get integrations for an account as a list of provider names.

    Args:
        account_id: Account UUID
        session: Database session (optional)

    Returns:
        List of integration provider names (e.g., ["toast", "opentable"]) or empty list
    """
    if not session:
        logger.warning(
            f"[Slackbot] get_account_integrations called with no session for account {account_id}"
        )
        return []

    try:
        from services import integration_service

        # Use integration service instead of direct database query
        integrations = integration_service.get_integrations_by_account_id(
            session, account_id
        )

        if not integrations:
            logger.info(f"[Slackbot] No integrations found for account {account_id}")
            return []

        # Return list of provider names (lowercase)
        provider_list = [integration.provider.value for integration in integrations]
        logger.info(
            f"[Slackbot] Found {len(provider_list)} integrations for account {account_id}: {provider_list}"
        )
        return provider_list

    except Exception as e:
        logger.warning(
            f"[Slackbot] Error looking up integrations for account {account_id}: {e}",
            exc_info=True,
        )
        return []


def get_account_timezone(session: Session, account_name: str) -> str:
    """
    Get the timezone for an account by looking up its first project's timezone.

    Args:
        session: Database session
        account_name: Account name to look up

    Returns:
        str: Timezone ID (e.g., 'America/Los_Angeles'), defaults to 'America/Los_Angeles' if not found
    """
    try:
        from db.tables.accounts import Account

        # Query account by name and join with projects to get timezone
        account = (
            session.query(Account).filter(Account.name.ilike(account_name)).first()
        )

        if account and account.projects:
            # Use the first project's timezone
            timezone = account.projects[0].timezone
            if timezone:
                logger.info(
                    f"[Slackbot] Found timezone '{timezone}' for account '{account_name}'"
                )
                return timezone

        logger.warning(
            f"[Slackbot] No timezone found for account '{account_name}', using default 'America/Los_Angeles'"
        )
        return "America/Los_Angeles"

    except Exception as e:
        logger.error(
            f"[Slackbot] Error looking up timezone for account '{account_name}': {e}"
        )
        return "America/Los_Angeles"
