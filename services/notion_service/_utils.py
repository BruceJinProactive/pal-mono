"""
Notion Utilities Module

Provides shared utility functions for Notion operations.
"""

import re
from typing import Optional

from utils.log import logger


async def extract_notion_page_id(notion_url: str) -> Optional[str]:
    """
    Extract Notion page ID from URL.

    Args:
        notion_url: The Notion page URL

    Returns:
        str: The page ID (32 hex chars without dashes), or None if extraction fails
    """
    try:
        parts = notion_url.split("/")
        if len(parts) > 0:
            page_id_part = parts[-1].split("?")[0]

            if len(page_id_part) >= 32:
                page_id = page_id_part[-32:]
                try:
                    int(page_id, 16)
                    logger.debug(
                        "[Feedback] Successfully extracted Notion page ID",
                        extra={
                            "notion_url": notion_url,
                            "page_id": page_id,
                        },
                    )
                    return page_id
                except ValueError:
                    match = re.search(r"([a-f0-9]{32})", page_id_part.lower())
                    if match:
                        return match.group(1)

        logger.warning(
            "[Feedback] Could not extract valid 32-character hex page ID from URL",
            extra={"notion_url": notion_url},
        )
        return None

    except Exception as e:
        logger.warning(
            f"[Feedback] Failed to extract Notion page ID from URL: {e}",
            extra={"notion_url": notion_url},
        )
        return None


def format_notion_page_id(page_id: str) -> str:
    """
    Format a Notion page ID into UUID format with dashes.

    Args:
        page_id: The Notion page ID (32 hex characters, with or without dashes)

    Returns:
        str: The formatted page ID with dashes (UUID format)

    Example:
        >>> format_notion_page_id("abcd1234ef5678901234567890abcdef")
        'abcd1234-ef56-7890-1234-567890abcdef'
    """
    if len(page_id) == 32 and "-" not in page_id:
        return (
            f"{page_id[:8]}-{page_id[8:12]}-"
            f"{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"
        )
    return page_id
