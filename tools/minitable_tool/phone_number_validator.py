import re


def validate_and_format_phone(phone: str) -> str:
    """
    Validate and format a phone number to +1(xxx)xxx-xxxx format.

    Args:
        phone: Raw phone number string

    Returns:
        Formatted phone number string in +1(xxx)xxx-xxxx format

    Raises:
        ValueError: If phone number is invalid or not a US number
    """
    if not phone:
        raise ValueError("Phone number is required")

    # Remove all non-digit characters
    digits_only = re.sub(r"\D", "", phone)

    # Handle different US phone number formats
    if len(digits_only) == 10:
        # 10 digits: assume US number
        area_code = digits_only[:3]
        exchange = digits_only[3:6]
        number = digits_only[6:]
    elif len(digits_only) == 11 and digits_only.startswith("1"):
        # 11 digits starting with 1: US number with country code
        area_code = digits_only[1:4]
        exchange = digits_only[4:7]
        number = digits_only[7:]
    else:
        raise ValueError(
            "Phone number format is invalid. Must be a valid US phone number (10 or 11 digits)"
        )

    # Validate area code and exchange
    if not _is_valid_area_code(area_code):
        raise ValueError(f"Phone number has invalid area code: {area_code}")

    if not _is_valid_exchange(exchange):
        raise ValueError(f"Phone number has invalid exchange code: {exchange}")

    # Format as +1 xxxxxxxxxx
    return f"+1 {area_code}{exchange}{number}"


def _is_valid_area_code(area_code: str) -> bool:
    """
    Validate US area code.

    Area codes cannot start with 0 or 1, and cannot have 9 as the second digit
    if the first digit is greater than 1.
    """
    if len(area_code) != 3:
        return False

    if area_code[0] in ["0", "1"]:
        return False

    # Area codes in format N9X where N > 1 are invalid
    if area_code[0] > "1" and area_code[1] == "9":
        return False

    return True


def _is_valid_exchange(exchange: str) -> bool:
    """
    Validate US exchange code.

    Exchange codes cannot start with 0.
    """
    if len(exchange) != 3:
        return False

    if exchange[0] == "0":
        return False

    return True
