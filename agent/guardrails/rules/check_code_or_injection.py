import re

from agent.guardrails.rules._constants import CODE_PATTERNS
from utils.log import logger


def check_code_or_injection(prompt: str) -> bool:
    """
    Rule 6:
    Detects programming code or potential malicious HTML injections in a given prompt.
    Returns a boolean indicating whether the input is safe (True) or contains suspicious
    patterns (False).
    """

    for pattern in CODE_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE | re.DOTALL):
            logger.info(f"Code or injection pattern detected: {pattern}")
            return False

    return True
