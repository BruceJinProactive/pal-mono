import re

from utils.log import logger

from . import _constants


def separate_concatenated_repeated(token: str) -> str:
    """
    Checks if the token is made up of repeated occurrences of a substring.
    If so, returns a space-separated version of that substring repeated.
    Otherwise, returns the token unchanged.
    """
    # Try every possible substring length from 1 up to half the token's length.
    for i in range(1, len(token) // 2 + 1):
        # Only consider lengths that evenly divide the token's length.
        if len(token) % i == 0:
            substring = token[:i]
            if substring * (len(token) // i) == token:
                # Found a repeated pattern; insert spaces between each occurrence.
                return " ".join([substring] * (len(token) // i))
    return token


def separate_concatenated_words_in_prompt(prompt: str) -> str:
    """
    Splits the prompt into tokens, checks each token for concatenated repeated words,
    and then reconstructs the prompt with separated words where applicable.
    """
    # We split on whitespace, this assumes words are separated by spaces.
    tokens = prompt.split()
    processed_tokens = [separate_concatenated_repeated(token) for token in tokens]
    return " ".join(processed_tokens)


def check_repeated(prompt: str) -> bool:
    """
    Rule 3: Checks for repeated words in a given prompt.
    Returns a boolean indicating whether the input is safe (True) or contains repeated words (False).
    """
    prompt = separate_concatenated_words_in_prompt(prompt)
    if re.compile(_constants.REPEATED_WORD_PATTERN, re.IGNORECASE).search(prompt):
        logger.warning("Repeated words found in prompt")
        return False
    return True
