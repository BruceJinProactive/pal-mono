"""
Postmark Service

Transactional email service for sending feedback-related notifications.
"""

from ._client import get_postmark_client, get_postmark_sender_email, reset_client
from ._email import send_feedback_receipt, send_resolution_notice

__all__ = [
    "get_postmark_client",
    "get_postmark_sender_email",
    "reset_client",
    "send_feedback_receipt",
    "send_resolution_notice",
]
