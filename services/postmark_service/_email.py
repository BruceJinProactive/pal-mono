"""
Postmark Email Sending Module

Provides functionality for sending transactional emails via Postmark.
"""

import asyncio

import requests

from utils.log import logger
from utils.secret import get_server_secret_with_fallback


def _send_postmark_request(
    url: str, payload: dict, headers: dict, timeout: int = 10
) -> requests.Response:
    """
    Helper function to send Postmark API request synchronously.

    This is a blocking function designed to be called via asyncio.to_thread().

    Args:
        url: Postmark API endpoint URL
        payload: JSON payload to send
        headers: HTTP headers including authentication token
        timeout: Request timeout in seconds (default: 10)

    Returns:
        Response object from requests

    Raises:
        requests.HTTPError: If the request fails
        requests.Timeout: If the request times out
    """
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response


async def _send_templated_email(
    user_email: str,
    template_alias: str,
    template_model: dict,
    success_log_message: str = "Email sent successfully",
    error_log_message: str = "Failed to send email",
) -> bool:
    """
    Helper function to send templated email via Postmark.

    Handles credential fetching, header construction, and request execution
    for all Postmark templated email operations.

    Args:
        user_email: Email address of the recipient
        template_alias: Postmark template alias to use
        template_model: Dictionary containing template variables
        success_log_message: Log message for successful send (default: "Email sent successfully")
        error_log_message: Log message for failed send (default: "Failed to send email")

    Returns:
        bool: True if email was sent successfully, False otherwise

    Note:
        - Uses POSTMARK_API_TOKEN from environment/secrets for authentication
        - Uses POSTMARK_SENDER_EMAIL from environment/secrets for the sender address
        - Failures are logged but do not raise exceptions
        - Network requests run off the event loop via asyncio.to_thread()
    """
    try:
        # Get credentials from AWS Secrets Manager
        api_token = get_server_secret_with_fallback("POSTMARK_API_TOKEN")
        sender_email = get_server_secret_with_fallback("POSTMARK_SENDER_EMAIL")

        # Construct the payload
        payload = {
            "From": sender_email,
            "To": user_email,
            "TemplateAlias": template_alias,
            "TemplateModel": template_model,
        }

        headers = {
            "X-Postmark-Server-Token": api_token,
            "Content-Type": "application/json",
        }

        # Send the email (run blocking network call off the event loop)
        await asyncio.to_thread(
            _send_postmark_request,
            "https://api.postmarkapp.com/email/withTemplate",
            payload,
            headers,
            10,  # 10 second timeout
        )

        logger.info(f"[Postmark] {success_log_message}")
        return True

    except Exception as e:
        logger.error(f"[Postmark] {error_log_message}: {e}")
        return False


async def send_feedback_receipt(
    user_email: str,
    user_name: str,
    feedback_text: str = "",
    product_name: str = "Palona",
    company_name: str = "Palona",
    support_email: str = "support@palona.ai",
    sender_name: str = "Palona FDE Team",
    help_url: str = "https://palona.ai/help",
) -> bool:
    """
    Send feedback receipt email to acknowledge user's feedback submission.

    This function sends a transactional email acknowledging that the user's
    feedback has been received using the 'feedback-received' Postmark template.

    Args:
        user_email: Email address of the user who submitted feedback
        user_name: Name of the user
        feedback_text: The feedback content submitted by the user
        product_name: Name of the product (default: "Palona")
        company_name: Name of the company (default: "Palona")
        support_email: Support email address (default: "support@palona.ai")
        sender_name: Name of the sender (default: "Palona FDE Team")
        help_url: URL for help documentation (default: "https://palona.ai/help")

    Returns:
        bool: True if email was sent successfully, False otherwise

    Note:
        - Uses POSTMARK_API_TOKEN from environment/secrets for authentication
        - Uses POSTMARK_SENDER_EMAIL from environment/secrets for the sender address
        - Template alias must be 'feedback-received' in Postmark dashboard
        - Failures are logged but do not raise exceptions
        - Network requests run off the event loop via asyncio.to_thread()
    """
    # Prepare the template data model
    template_model = {
        "product_name": product_name,
        "name": user_name,
        "feedback_text": feedback_text,
        "company_name": company_name,
        "support_email": support_email,
        "sender_name": sender_name,
        "help_url": help_url,
    }

    return await _send_templated_email(
        user_email=user_email,
        template_alias="feedback-received",
        template_model=template_model,
        success_log_message="Feedback receipt email sent",
        error_log_message="Failed to send feedback receipt email",
    )


async def send_resolution_notice(
    user_email: str,
    user_name: str = "Valued Customer",
    submission_date: str = "",
    tags: list[str] | None = None,
    feedback_content: str = "",
    action_url: str = "",
    product_name: str = "Palona",
    product_url: str = "https://palona.ai",
    company_name: str = "Palona",
    support_email: str = "support@palona.ai",
    sender_name: str = "Palona FDE Team",
    help_url: str = "https://palona.ai/help",
    phone_number: str = "",
) -> bool:
    """
    Send resolution notice email when feedback has been resolved.

    This function sends a transactional email notifying the user that their
    feedback has been resolved and changes are now live using the 'feedback-resolved'
    Postmark template. It handles missing data gracefully with sensible defaults.

    Args:
        user_email: Email address of the user who submitted feedback
        user_name: Name of the user (defaults to "Valued Customer" if not provided)
        submission_date: Date when feedback was submitted (defaults to "recently")
        tags: List of feedback tags (defaults to empty list)
        feedback_content: The original feedback content (defaults to generic message)
        action_url: URL to view the conversation (defaults to console URL)
        product_name: Name of the product (default: "Palona")
        product_url: URL to the product (default: "https://palona.ai")
        company_name: Name of the company (default: "Palona")
        support_email: Support email address (default: "support@palona.ai")
        sender_name: Name of the sender (default: "Palona FDE Team")
        help_url: URL for help documentation (default: "https://palona.ai/help")
        phone_number: Optional phone number to test the agent (default: "")

    Returns:
        bool: True if email was sent successfully, False otherwise

    Note:
        - Uses POSTMARK_API_TOKEN from environment/secrets for authentication
        - Uses POSTMARK_SENDER_EMAIL from environment/secrets for the sender address
        - Template alias must be 'feedback-resolved' in Postmark dashboard
        - This function is designed to work even with minimal data
        - Failures are logged but do not raise exceptions
        - Network requests run off the event loop via asyncio.to_thread()
    """
    # Use defaults for missing data
    if tags is None:
        tags = []

    if not submission_date:
        submission_date = "recently"

    if not action_url:
        action_url = "https://console.palona.ai"

    # Prepare the template data model
    template_model = {
        "product_url": product_url,
        "product_name": product_name,
        "name": user_name,
        "submission_date": submission_date,
        "tags": ", ".join(tags) if tags else "General",
        "feedback_content": feedback_content,
        "action_url": action_url,
        "company_name": company_name,
        "support_email": support_email,
        "sender_name": sender_name,
        "help_url": help_url,
        "phone_number": phone_number,
    }

    return await _send_templated_email(
        user_email=user_email,
        template_alias="feedback-resolved",
        template_model=template_model,
        success_log_message="Resolution notice email sent",
        error_log_message="Failed to send resolution notice email",
    )


async def send_feedback_backlog(
    user_email: str,
    user_name: str = "Valued Customer",
    submission_date: str = "",
    feedback_text: str = "",
    conversation_url: str = "",
    product_name: str = "Palona",
    company_name: str = "Palona",
    support_email: str = "support@palona.ai",
    sender_name: str = "Palona FDE Team",
    help_url: str = "https://palona.ai/help",
) -> bool:
    """
    Send feedback backlog notice when feedback is deferred.

    This function sends a transactional email notifying the user that their
    feedback is being worked on but requires more time using the 'feedback-backlog'
    Postmark template.

    Args:
        user_email: Email address of the user who submitted feedback
        user_name: Name of the user (defaults to "Valued Customer" if not provided)
        submission_date: Date when feedback was submitted (defaults to "recently")
        feedback_text: The feedback content submitted by the user
        conversation_url: URL to view the conversation
        product_name: Name of the product (default: "Palona")
        company_name: Name of the company (default: "Palona")
        support_email: Support email address (default: "support@palona.ai")
        sender_name: Name of the sender (default: "Palona FDE Team")
        help_url: URL for help documentation (default: "https://palona.ai/help")

    Returns:
        bool: True if email was sent successfully, False otherwise

    Note:
        - Uses POSTMARK_API_TOKEN from environment/secrets for authentication
        - Uses POSTMARK_SENDER_EMAIL from environment/secrets for the sender address
        - Template alias must be 'feedback-backlog' in Postmark dashboard
        - Failures are logged but do not raise exceptions
        - Network requests run off the event loop via asyncio.to_thread()
    """
    # Use defaults for missing data
    if not submission_date:
        submission_date = "recently"

    if not conversation_url:
        conversation_url = "https://console.palona.ai"

    # Prepare the template data model
    template_model = {
        "product_name": product_name,
        "name": user_name,
        "submission_date": submission_date,
        "feedback_text": feedback_text,
        "conversation_url": conversation_url,
        "company_name": company_name,
        "support_email": support_email,
        "sender_name": sender_name,
        "help_url": help_url,
    }

    return await _send_templated_email(
        user_email=user_email,
        template_alias="feedback-backlog",
        template_model=template_model,
        success_log_message="Feedback backlog email sent",
        error_log_message="Failed to send feedback backlog email",
    )
