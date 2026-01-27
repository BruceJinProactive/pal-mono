"""
Notion Service

Provides both generic Notion page management and domain-specific helpers (feedback, etc.).

Structure:
- _client: Notion client initialization
- _pages: Generic page operations (create_page, update_page_properties)
- _properties: Property/block builders (build_title_property, etc.)
- _feedback: Feedback-specific helpers (create_feedback_ticket, etc.)
- _utils: General utilities (format_notion_page_id, etc.)

Generic Functions:
- create_page: Create pages in any Notion database
- update_page_properties: Update properties of any Notion page

Property Builders:
- build_title_property, build_rich_text_property, build_select_property, etc.

Domain-Specific Functions:
- create_feedback_ticket: Convenience wrapper for feedback tickets
- update_feedback_status: Convenience wrapper for feedback status updates
"""

from ._client import get_notion_client
from ._feedback import (
    create_feedback_ticket,
    get_client_page_id_by_account_name,
    update_feedback_status,
)
from ._pages import create_page, update_page_properties
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
from ._utils import extract_notion_page_id, format_notion_page_id

__all__ = [
    # Generic page operations
    "create_page",
    "update_page_properties",
    # Property builders
    "build_title_property",
    "build_rich_text_property",
    "build_select_property",
    "build_multi_select_property",
    "build_email_property",
    "build_url_property",
    "build_relation_property",
    "build_paragraph_block",
    # Domain-specific (feedback)
    "create_feedback_ticket",
    "update_feedback_status",
    "get_client_page_id_by_account_name",
    # Utilities
    "extract_notion_page_id",
    "format_notion_page_id",
    "get_notion_client",
]
