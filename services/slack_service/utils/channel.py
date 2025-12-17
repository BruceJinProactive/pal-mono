"""
Channel Verification and Authorization Utilities

This module handles:
- Channel name extraction
- Account extraction from client channels
- Channel-based authorization
- Account lookup by name
"""

import uuid

from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session

from utils.log import logger

# Internal channels that can see all account data
INTERNAL_CHANNELS = {
    "agent-performance",
    "test-channel",
    "#agent-performance",
    "#test-channel",
}


async def get_channel_name(client: AsyncWebClient, channel_id: str) -> str:
    """
    Get human-readable channel name from channel ID.

    Args:
        client: Slack async web client
        channel_id: Slack channel ID (e.g., 'C09BT1E5E7M')

    Returns:
        Channel name with # prefix (e.g., '#general') or original ID if lookup fails
    """
    try:
        response = await client.conversations_info(channel=channel_id)
        if response and response.get("ok"):
            channel_info = response.get("channel")
            if channel_info:
                channel_name = channel_info.get("name")
                if channel_name:
                    return f"#{channel_name}"
    except Exception as e:
        logger.warning(f"[Slackbot] Failed to get channel name for {channel_id}: {e}")

    # Fallback to channel ID if lookup fails
    return channel_id


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


def extract_account_from_channel(channel_display_name: str) -> str | None:
    """
    Extract account name from client channel names.

    For channels in format "#client-account-name", extracts "account-name".

    Args:
        channel_display_name: Channel name (e.g., "#client-acme-restaurant")

    Returns:
        str | None: Account name if channel is a client channel, None otherwise
    """
    normalized = channel_display_name.strip().lstrip("#").lower()
    if normalized.startswith("client-"):
        # Extract everything after "client-"
        account_name = normalized[7:]  # len("client-") = 7
        return account_name if account_name else None
    return None


def determine_account_filter(
    channel: str,
    session: Session,
    account_name: str | None = None,
    channel_display_name: str | None = None,
) -> tuple[uuid.UUID | None, str | None]:
    """
    Determine which account(s) to show based on channel and optional account name.

    For client channels (starting with "client-"):
    - Extracts account name from channel (e.g., #client-acme-restaurant -> acme-restaurant)
    - If user provides account name via "for", validates first 3 characters match
    - If no account name provided, auto-uses channel's account

    Priority:
    1. If in internal channel -> show all accounts (return None)
    2. If channel starts with "client-" -> extract account from channel name
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
