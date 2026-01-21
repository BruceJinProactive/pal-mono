"""
Postmark Client Management Module

Provides centralized Postmark client creation and management.
"""

import threading
from typing import Optional

from postmarker.core import PostmarkClient

from utils.log import logger

# Global client instance for reuse
_client_instance: PostmarkClient | None = None
# Thread lock for synchronizing client access
_client_lock = threading.Lock()


def get_postmark_client() -> Optional[PostmarkClient]:
    """
    Get or create a Postmark client instance.

    CURRENTLY DISABLED: Returns None.

    Uses a singleton pattern to reuse the same client instance.
    Fetches the API token from environment or AWS Secrets Manager on first use.

    Returns:
        Optional[PostmarkClient]: Configured Postmark client, or None if disabled

    Raises:
        ValueError: If no token available
    """
    # DISABLED: Postmark client creation is currently disabled
    logger.debug("[Postmark] Client creation disabled - returning None")
    return None


def get_postmark_sender_email() -> str:
    """
    Get the Postmark sender email from environment variables.

    Returns:
        str: The verified sender email address

    Raises:
        ValueError: If sender email is not configured
    """
    # sender_email = os.environ.get("POSTMARK_SENDER_EMAIL")
    # if not sender_email:
    #     logger.error("[Postmark] POSTMARK_SENDER_EMAIL not configured")
    #     raise ValueError("Postmark sender email not configured")
    # return sender_email
    return ""


def reset_client() -> None:
    """
    Reset the cached Postmark client instance.

    This is useful for testing or when credentials change.
    """
    global _client_instance
    with _client_lock:
        _client_instance = None
    logger.debug("[Postmark] Client instance reset")
