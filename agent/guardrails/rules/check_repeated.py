import re

from utils.log import logger

# Regex for repeated words (e.g., "hack hack hack")
REPEATED_WORD_PATTERN = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)


def check_repeated(prompt: str) -> bool:
    """
    Rule 3: Checks for repeated words in a given prompt.
    Returns a boolean indicating whether the input is safe (True) or contains repeated words (False).
    """
    if REPEATED_WORD_PATTERN.search(prompt):
        logger.info("Repeated words found in prompt")
        return False
    return True
