from utils.log import logger

from . import _constants


def check_length(prompt: str) -> bool:
    """
    Rule 1: Checks if the prompt exceeds the maximum allowed word count.
    Returns False if the prompt is too long.
    """
    if len(prompt.strip().split()) > _constants.MAX_PROMPT_LENGTH:
        logger.info(f"Prompt length exceeded: {len(prompt)}")
        return False
    return True
