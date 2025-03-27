import re

from utils.log import logger

from . import _constants


def check_encoded_text(prompt: str) -> bool:
    """
    Rule 5: Checks for Base64, Hex, Octal encoding, or presence of non-printable ASCII.
    These patterns are often used to obfuscate malicious content.
    """
    base64_pattern = re.compile(_constants.BASE64)
    binary_pattern = re.compile(_constants.BINARY)
    decimal_pattern = re.compile(_constants.DECIMAL)
    hex_pattern = re.compile(_constants.HEX)
    octal_pattern = re.compile(_constants.OCTAL)
    ascii_pattern = re.compile(_constants.ASCII)

    if any(
        pattern.search(prompt)
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
