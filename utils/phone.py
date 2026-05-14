"""Utilities for phone number classification."""

from utils.log import logger
from utils.secret import get_server_secret_with_fallback


def get_test_phone_numbers() -> set[str]:
    """
    Return the configured set of test/internal phone numbers.

    Reads from AWS Secrets Manager (or env var fallback) TEST_PHONE_NUMBERS,
    which should be a comma-separated list of E.164 phone numbers.

    Returns:
        Set of phone number strings (empty if not configured).
    """
    try:
        test_numbers_str = get_server_secret_with_fallback("TEST_PHONE_NUMBERS")
    except (ValueError, KeyError):
        logger.warning(
            "[phone] TEST_PHONE_NUMBERS secret not configured — "
            "test number exclusion disabled"
        )
        return set()

    if not test_numbers_str:
        return set()

    return {num.strip() for num in test_numbers_str.split(",") if num.strip()}


def is_test_phone_number(phone_number: str) -> bool:
    """
    Check if a phone number is a Palona test/internal number.

    Args:
        phone_number: Phone number to check (E.164 format).

    Returns:
        True if test number, False otherwise.
    """
    return phone_number in get_test_phone_numbers()
