from utils.log import logger

from . import _constants


def check_special_characters(prompt: str) -> bool:
    """
    Rule 4: Checks for excessive use of special characters.
    If special characters exceed 30% of the prompt, it flags it as suspicious.
    """
    special_chars_count = sum(
        1 for char in prompt if char not in _constants.ALLOWED_CHARACTERS
    )
    if special_chars_count / max(1, len(prompt)) > 0.3:
        logger.warning("Excessive special characters found in prompt")
        return False
    return True
