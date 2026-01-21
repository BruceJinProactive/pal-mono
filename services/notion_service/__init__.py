"""
Notion Service

Provides functionality for creating and managing Notion tickets for feedback.
"""

from ._client import get_notion_client
from ._tickets import create_feedback_ticket, update_feedback_status

__all__ = ["create_feedback_ticket", "get_notion_client", "update_feedback_status"]
