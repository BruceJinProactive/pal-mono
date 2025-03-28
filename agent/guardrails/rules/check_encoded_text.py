import re

from utils.log import logger

from . import _constants


def check_encoded_text(prompt: str) -> bool:
    """
    Rule 5: Checks for Base64, Hex, Octal encoding, or presence of non-printable ASCII.
    These patterns are often used to obfuscate malicious content.
    """
    # Compile removal patterns.
    patterns_to_remove = [
        re.compile(_constants.PHONE_PATTERN, re.IGNORECASE),
        re.compile(_constants.UNITS_PATTERN, re.IGNORECASE),
        re.compile(_constants.POSTAL_CODE_PATTERN, re.IGNORECASE),
    ]

    # Remove substrings matching any of the whitelisted patterns.
    filtered_prompt = prompt

    for pattern in patterns_to_remove:
        filtered_prompt = pattern.sub("__REMOVED__", filtered_prompt)
    logger.info(f"Filtered prompt for encoded txt check: {filtered_prompt}")

    base64_pattern = re.compile(_constants.BASE64)
    binary_pattern = re.compile(_constants.BINARY)
    decimal_pattern = re.compile(_constants.DECIMAL)
    hex_pattern = re.compile(_constants.HEX)
    octal_pattern = re.compile(_constants.OCTAL)
    ascii_pattern = re.compile(_constants.ASCII)

    if any(
        pattern.search(filtered_prompt)
        for pattern in (
            base64_pattern,
            binary_pattern,
            decimal_pattern,
            hex_pattern,
            octal_pattern,
            ascii_pattern,
        )
    ):
        logger.info("Encoded text found in prompt")
        return False
    return True
