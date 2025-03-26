import unicodedata

from agent.guardrails.rules._constants import (
    ALLOWED_PUNCTUATION,
    ALLOWED_WHITE_SPACE,
    BANNED_CATEGORIES,
)
from utils.log import logger


def is_emoji(char: str) -> bool:
    """Returns True if the character is an emoji, False otherwise"""
    ord_char = ord(char)
    return (
        0x1F300 <= ord_char <= 0x1F6FF  # Emoticons & Symbols
        or 0x1F900 <= ord_char <= 0x1F9FF  # Supplemental Symbols and Pictographs
        or 0x2600 <= ord_char <= 0x26FF  # Miscellaneous Symbols
        or unicodedata.category(char) in ("So", "Sk")  # Symbols & Modifiers
    )


def check_unicode(prompt: str) -> bool:
    """
    Rule 7: Flags invisible characters, emojis, and symbols outside allowed ranges.
    Prevents use of hidden Unicode or special characters to bypass filters.
    """
    for char in prompt:
        char_ord = ord(char)

        # Check for non-ASCII characters that are not allowed.
        if (
            char_ord > 127
            and not is_emoji(char)
            and char not in ALLOWED_WHITE_SPACE
            and char not in ALLOWED_PUNCTUATION
        ):
            message = f"Non-ASCII character found: {char} (ord: {char_ord})"
            logger.info(message)
            return False

        # Check for characters in banned Unicode categories.
        if (
            unicodedata.category(char) in BANNED_CATEGORIES
            and char not in ALLOWED_WHITE_SPACE
        ):
            message = f"Banned Unicode category '{unicodedata.category(char)}' found for character: {char}"
            logger.info(message)
            return False
    return True
