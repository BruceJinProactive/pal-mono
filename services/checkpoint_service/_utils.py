"""Utility functions for checkpoint service."""

from datetime import datetime


class TimestampValidationError(Exception):
    """Exception raised when timestamp validation fails."""

    pass


def parse_and_validate_timestamp(timestamp_str: str) -> datetime:
    """
    Parse and validate an ISO 8601 timestamp string with timezone.

    This function handles timestamps with timezone information provided by the client,
    ensuring proper handling of users in different time zones.

    Args:
        timestamp_str: ISO 8601 timestamp string with timezone
                      (e.g., "2025-09-17T00:00:00-07:00" or "2025-09-17T00:00:00+00:00")

    Returns:
        datetime: Parsed datetime object with timezone info

    Raises:
        TimestampValidationError: If timestamp format is invalid or missing timezone

    """
    if not timestamp_str:
        raise TimestampValidationError("Timestamp cannot be empty")

    try:
        # Parse ISO 8601 timestamp with timezone
        parsed_datetime = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

        # Ensure the timestamp has timezone information
        if parsed_datetime.tzinfo is None:
            raise TimestampValidationError(
                f"Timestamp must include timezone information: {timestamp_str}. "
                f"Expected format: '2025-09-17T00:00:00-07:00' or '2025-09-17T00:00:00+00:00'"
            )

        return parsed_datetime

    except (ValueError, AttributeError) as e:
        raise TimestampValidationError(
            f"Invalid timestamp format: {timestamp_str}. "
            f"Expected ISO 8601 format with timezone (e.g., '2025-09-17T00:00:00-07:00'). "
            f"Error: {str(e)}"
        )
