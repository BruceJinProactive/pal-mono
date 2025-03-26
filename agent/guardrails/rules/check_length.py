from agent.guardrails.rules._constants import MAX_PROMPT_LENGTH
from utils.log import logger


def check_length(prompt: str) -> bool:
    """
    Rule 1: Checks if the prompt exceeds the maximum allowed word count.
    Returns False if the prompt is too long.
    """
    if len(prompt.strip().split()) > MAX_PROMPT_LENGTH:
        logger.info(f"Prompt length exceeded: {len(prompt)}")
        return False
    return True
