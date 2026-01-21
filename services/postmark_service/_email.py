"""
Postmark Email Sending Module

Provides functionality for sending transactional emails via Postmark.

NOTE: Email sending is currently DISABLED.
"""

from typing import Optional

from utils.log import logger


async def send_feedback_receipt(
    user_email: str,
    user_name: Optional[str] = None,
) -> bool:
    """
    Send a feedback receipt email to the user.

    This function sends a transactional email confirming that
    feedback has been received and is being reviewed.

    Args:
        user_email: Email address of the user who submitted feedback
        user_name: Name of the user (optional, defaults to email if not provided)

    Returns:
        bool: True if email was sent successfully, False otherwise

    Note:
        - CURRENTLY DISABLED: Email sending is disabled
        - Uses POSTMARK_API_TOKEN from environment/secrets for authentication
        - Uses POSTMARK_SENDER_EMAIL for the sender address
        - Failures are logged but do not raise exceptions
    """
    # DISABLED: Email sending is currently disabled
    logger.info("[Postmark] Email sending disabled - skipping feedback receipt email")
    return True


async def send_resolution_notice(
    user_email: str,
    user_name: Optional[str] = None,
) -> bool:
    """
    Send a resolution notice email to the user.

    This function sends a transactional email notifying the user that
    changes related to their feedback are now live.

    Args:
        user_email: Email address of the user who submitted feedback
        user_name: Name of the user (optional, defaults to email if not provided)

    Returns:
        bool: True if email was sent successfully, False otherwise

    Note:
        - CURRENTLY DISABLED: Email sending is disabled
        - Uses POSTMARK_API_TOKEN from environment/secrets for authentication
        - Uses POSTMARK_SENDER_EMAIL for the sender address
        - This email is only sent when the 'Changes Now Live' button is clicked in Slack
        - Failures are logged but do not raise exceptions
    """
    # DISABLED: Email sending is currently disabled
    logger.info("[Postmark] Email sending disabled - skipping resolution notice email")
    return True
