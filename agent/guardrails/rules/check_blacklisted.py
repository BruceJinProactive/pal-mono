import re

from utils.log import logger

from . import _constants


def check_blacklisted(prompt: str) -> bool:
    """
    Rule 2: Checks for presence of blacklisted words/phrases.
    - Converts prompt to lowercase for case-insensitive comparison.
    """
    prompt_lower = prompt.lower()
    styled_dan_pattern = r"\bd(?:[^\w\s]+)a(?:[^\w\s]+)n\b"
    if re.search(styled_dan_pattern, prompt_lower):
        """Uses a generalized regex to detect styled variants of dan. This regex matches the letter d, followed by one or more non-alphanumeric/non-whitespace (special/unicode) characters, then a, then again one or more special characters, then n.
        it should catch styled variants like "DAN", "d-a-n", "d🔥A🔥n","""
        logger.info("Blacklisted styled DAN pattern found in prompt")
        return False
    words = set(prompt_lower.split())
    blacklist_set = set(_constants.BLACKLIST)

    if words.intersection(blacklist_set):
        logger.info("Blacklisted word found in prompt")
        return False
    return True
