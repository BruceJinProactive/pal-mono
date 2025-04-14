#### NOTE: Most of the logics in this file are borrowed from Adora. ####
import re

from tools.toast_tool.classes import DiningBehavior


def format_phone_number(phone_number: str) -> str:
    # Remove non-digit characters
    digits = re.sub(r"\D", "", phone_number)

    # Ensure it has 10 digits (remove US country code if present)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]

    # Validate the number has exactly 10 digits
    if len(digits) != 10:
        return ""

    return digits


def is_valid_phone_number(phone_number: str) -> bool:
    pattern = r"^\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})$"
    return re.match(pattern, phone_number) is not None


def is_valid_email(email: str) -> bool:
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None


def validate_order_type(order_type: DiningBehavior) -> DiningBehavior:
    if order_type == DiningBehavior.TAKE_OUT:
        return order_type
    raise ValueError(f"Invalid order type: {order_type}")
