"""
Postmark Client Management Module

Provides centralized Postmark client creation and management.
"""

import threading

from postmarker.core import PostmarkClient

from utils.log import logger
from utils.secret import get_server_secret_with_fallback

# Global client instance for reuse
_client_instance: PostmarkClient | None = None
# Thread lock for synchronizing client access
_client_lock = threading.Lock()


def get_postmark_client() -> PostmarkClient:
    """
    Get or create a Postmark client instance.

    Uses a singleton pattern to reuse the same client instance.
    Fetches the API token from environment or AWS Secrets Manager on first use.

    Returns:
        PostmarkClient: Configured Postmark client

    Raises:
        ValueError: If no token available
    """
    global _client_instance

    with _client_lock:
        if _client_instance is None:
            try:
                api_token = get_server_secret_with_fallback("POSTMARK_API_TOKEN")
                if not api_token:
                    logger.error("[Postmark] POSTMARK_API_TOKEN not configured")
                    raise ValueError("Postmark API token not configured")

                _client_instance = PostmarkClient(server_token=api_token)
                logger.debug("[Postmark] Client instance created successfully")
            except Exception as e:
                logger.error(f"[Postmark] Failed to create client: {e}")
                raise

    return _client_instance


def get_postmark_sender_email() -> str:
    """
    Get the Postmark sender email from environment variables or AWS Secrets Manager.

    Returns:
        str: The verified sender email address

    Raises:
        ValueError: If sender email is not configured
    """
    try:
        sender_email = get_server_secret_with_fallback("POSTMARK_SENDER_EMAIL")
        if not sender_email:
            logger.error("[Postmark] POSTMARK_SENDER_EMAIL not configured")
            raise ValueError("Postmark sender email not configured")
        return sender_email
    except Exception as e:
        logger.error(f"[Postmark] Failed to get sender email: {e}")
        raise


def reset_client() -> None:
    """
    Reset the cached Postmark client instance.

    This is useful for testing or when credentials change.
    """
    global _client_instance
    with _client_lock:
        _client_instance = None
    logger.debug("[Postmark] Client instance reset")
