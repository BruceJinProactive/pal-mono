import re
from typing import Any

from utils.log import logger


def strip_markdown_content(agent_message: Any) -> Any | str:
    """
    Strip the given agent message by removing markdown formatting.

    This function processes the input string to:
    1. Remove bold markdown (**text**).
    2. Replace markdown links ([text](URL)) with just the URLs.
    3. Remove leading exclamation marks from URLs (left over from image markdown).

    Args:
        agent_message (Any): The message content to be stripped of markdown. If the input is not a string, it will be returned as is.

    Returns:
        Any | str: The stripped message content if the input was a string, otherwise the original input.
    """
    # Only process if agent_message if it is a string
    if not isinstance(agent_message, str):
        return agent_message

    # Remove bold markdown
    agent_message = re.sub(r"\*\*(.*?)\*\*", r"\1", agent_message)

    # Remove markdown links and replace with URLs
    agent_message = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\2", agent_message)

    # Remove leading exclamation mark from URLs (left over from image markdown)
    agent_message = re.sub(r"!\s*(https?://[^\s]+)", r"\1", agent_message)

    return agent_message


def extract_image_links(response: str) -> list[tuple[str, str]]:
    """
    Process response text to extract image URLs
    Returns the original text and any image URLs found.

    Args:
        response: The response text to process

    Returns:
        list[tuple[str, str]]: List of tuples containing (type, content)
            where type is either "text" or "image"
    """
    processed_parts = []

    # 1. Keep response text unchanged
    if response.strip():
        processed_parts.append(("text", response))

    # 2. Extract image URLs
    pattern = r"""
        (https?:\/\/                # http:// or https://
        [^\s)]+\.                  # URL path until extension (no spaces or closing parens)
        (?i:                       # Case insensitive match for extensions
            jpg|jpeg|png|apng|     # Common image formats
            gif|webp|svg|bmp|      # More image formats
            tiff?|ico|             # Even more formats
            heic|heif|avif|        # Modern formats
            jfif|pjpeg|pjp         # JPEG variants
        )
        (?:\/[^\s)]*)?            # Optional additional path segments
        (?:[?#][^\s)]*)?          # Optional query params or hash fragments
        )
    """
    try:
        image_urls = re.findall(pattern, response, re.VERBOSE)
        for url in image_urls:
            processed_parts.append(("image", url))
    except re.error as e:
        logger.error(f"Error extracting image URLs: {e}")

    return processed_parts
