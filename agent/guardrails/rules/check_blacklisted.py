import re

from utils.log import logger

from . import _constants


def check_blacklisted(prompt: str) -> bool:
    """
    Rule 2: Checks for presence of blacklisted words/phrases.
    - Converts prompt to lowercase for case-insensitive comparison.
    """
    prompt_lower = prompt.strip().lower()
    if re.search(_constants.DAN_PATTERN, prompt_lower):
        """Uses a generalized regex to detect styled variants of dan. This regex matches the letter d, followed by one or more non-alphanumeric/non-whitespace (special/unicode) characters, then a, then again one or more special characters, then n.
        it should catch styled variants like "DAN", "d-a-n", "d🔥A🔥n","""
        logger.info("Blacklisted styled DAN pattern found in prompt")
        return False

    # Check for blacklisted phrases using regex for case-insensitive matching.
    for phrase in _constants.BLACKLIST:
        # re.escape makes sure any special regex characters in phrase are treated literally.
        if re.search(re.escape(phrase), prompt, re.IGNORECASE):
            logger.info(f"Blacklisted phrase found in prompt: {phrase}")
            return False

    return True
