"""
Base class for reservation and waitlist tools.

This module provides a common interface for reservation tools like MiniTable and OpenTable.
"""

from abc import ABC, abstractmethod
from functools import wraps
from typing import Any, Dict, List, Optional


def params_validate():
    """Decorator that auto-detects required fields based on method name.

    Expects a class attribute named REQUIRED_{METHOD_NAME}_FIELDS.
    For example: make_reservation -> REQUIRED_MAKE_RESERVATION_FIELDS
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Auto-generate attribute name based on method name
            auto_attr = f"REQUIRED_{func.__name__.upper()}_FIELDS"

            # Check if required fields attribute exists
            if hasattr(self, auto_attr):
                required_fields = getattr(self, auto_attr)

                # Check it's not empty
                if not required_fields:
                    raise ValueError(
                        f"Required fields attribute {auto_attr} cannot be empty "
                        f"for method {func.__name__} in {self.__class__.__name__}"
                    )

                # Only validate when called with kwargs (tool methods typically use kwargs)
                if kwargs:
                    validation_error = self.validate_required_params(
                        kwargs, required_fields, func.__name__
                    )
                    if validation_error:
                        return validation_error

            return func(self, *args, **kwargs)

        return wrapper

    return decorator


class BaseReservationTool(ABC):
    """
    Abstract base class for reservation/waitlist tools.

    Provides common interface for tools that handle restaurant reservations,
    availability checking, and waitlist management.

    IMPORTANT FOR IMPLEMENTERS:
    - Each implementation MUST provide detailed docstrings for LLM consumption
    - Docstrings are critical as they guide the LLM on how to use the tool
    - Specify exact parameter types, formats, and whether they are optional
    - Include tool-specific validation rules and examples in docstrings
    - Use **kwargs for tool-specific parameters not covered in base interface
    """

    @abstractmethod
    def check_availability(self, party_size: int, date: str, time: str) -> str:
        """
        Check availability for restaurant reservations.

        Args:
            party_size: Number of people for the reservation
            date: Date for the reservation in YYYY-MM-DD format
            time: Time for the reservation in HH:MM format (24-hour)

        Returns:
            str: Availability status and alternative suggestions if applicable
        """
        raise NotImplementedError

    @abstractmethod
    def make_reservation(
        self,
        name: str,
        party_size: int,
        date: str,
        time: str,
        email: str = "",
        notes: str = "",
    ) -> str:
        """
        Make a reservation at the restaurant.

        Args:
            name: Customer name
            party_size: Number of people for the reservation
            date: Date for the reservation in YYYY-MM-DD format
            time: Time for the reservation in HH:MM format (24-hour)
            email: Customer email address (optional)
            notes: Optional notes for the reservation

        Returns:
            str: Reservation confirmation details or error message
        """
        raise NotImplementedError

    @abstractmethod
    def get_waitlist_status(self) -> str:
        """
        Get current waitlist status and wait times for the restaurant.

        Returns:
            str: Current waitlist status, wait times, and availability information
        """
        raise NotImplementedError

    @abstractmethod
    def join_waitlist_queue(
        self,
        name: str,
        party_size: int,
        notes: str = "",
    ) -> str:
        """
        Join the waitlist queue for the restaurant.

        Args:
            name: Customer name
            party_size: Number of people in the party
            notes: Optional notes for the waitlist entry

        Returns:
            str: Waitlist confirmation details or error message
        """
        raise NotImplementedError

    @abstractmethod
    def get_user_wait_status(self) -> str:
        """
        Get today's waitlist entries for a specific phone number.

        Args:
            None

        Returns:
            str: Waitlist entries and status information for the phone number
        """
        raise NotImplementedError

    def validate_required_params(
        self, params: Dict[str, Any], required_fields: List[str], method_name: str = ""
    ) -> Optional[str]:
        """
        Validate that required parameters are not empty.

        Args:
            params: Dictionary of parameter names to values
            required_fields: List of parameter names that are required
            method_name: Name of the method being validated (for error messages)

        Returns:
            str: Error message if validation fails, None if validation passes
        """
        missing_fields = []
        empty_fields = []

        for field in required_fields:
            if field not in params:
                missing_fields.append(field)
            elif not str(params[field]).strip():
                empty_fields.append(field)

        if missing_fields or empty_fields:
            method_info = f" for {method_name}" if method_name else ""
            error_parts = []

            if missing_fields:
                error_parts.append(
                    f"Missing required fields: {', '.join(missing_fields)}"
                )
            if empty_fields:
                error_parts.append(f"Empty required fields: {', '.join(empty_fields)}")

            return f"Validation error{method_info}. {'. '.join(error_parts)}"

        return None
