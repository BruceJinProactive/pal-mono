"""
Message Parsing Utilities

This module handles generic message parsing functions that can be reused
across different Slack command handlers.
"""

import re


def parse_account_name_from_message(message_text: str) -> str | None:
    """
    Parse account name from message text like "daily for acme-restaurant".
    Only supports "for" keyword format.

    Args:
        message_text: The full message text from Slack

    Returns:
        str | None: Account name if found, None otherwise
    """
    # Pattern: "for account_name" (case insensitive)
    match = re.search(r"for\s+([a-zA-Z0-9_-]+)", message_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return None
