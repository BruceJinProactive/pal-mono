# Constants for validation
VALID_PHONE_PATTERN = r"^\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})$"
# TODO: Consider using email-validator library instead of regex
VALID_EMAIL_PATTERN = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
VALID_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
