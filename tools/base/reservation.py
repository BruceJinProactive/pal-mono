"""
Base class for reservation and waitlist tools.

This module provides a common interface for reservation tools like MiniTable and OpenTable.
"""

from abc import ABC, abstractmethod


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
    def check_availability(
        self, party_size: int, date: str, time: str, **kwargs
    ) -> str:
        """
        Check availability for restaurant reservations.

        Args:
            party_size: Number of people for the reservation
            date: Date for the reservation in YYYY-MM-DD format
            time: Time for the reservation in HH:MM format (24-hour)
            **kwargs: Additional tool-specific parameters

        Returns:
            str: Availability status and alternative suggestions if applicable
        """
        raise NotImplementedError

    @abstractmethod
    def make_reservation(
        self,
        phone: str,
        first_name: str,
        last_name: str,
        email: str,
        party_size: int,
        date: str,
        time: str,
        notes: str = "",
        **kwargs,
    ) -> str:
        """
        Make a reservation at the restaurant.

        Args:
            phone: Customer phone number (format may vary by tool)
            first_name: Customer first name
            last_name: Customer last name
            email: Customer email address
            party_size: Number of people for the reservation
            date: Date for the reservation in YYYY-MM-DD format
            time: Time for the reservation in HH:MM format (24-hour)
            notes: Optional notes for the reservation
            **kwargs: Additional tool-specific parameters

        Returns:
            str: Reservation confirmation details or error message
        """
        raise NotImplementedError

    @abstractmethod
    def get_waitlist_status(self, **kwargs) -> str:
        """
        Get current waitlist status and wait times for the restaurant.

        Args:
            **kwargs: Additional tool-specific parameters

        Returns:
            str: Current waitlist status, wait times, and availability information
        """
        raise NotImplementedError

    @abstractmethod
    def join_waitlist_queue(
        self,
        first_name: str,
        last_name: str,
        phone: str,
        party_size: int,
        notes: str = "",
        **kwargs,
    ) -> str:
        """
        Join the waitlist queue for the restaurant.

        Args:
            first_name: Customer first name
            last_name: Customer last name
            phone: Customer phone number
            party_size: Number of people in the party
            notes: Optional notes for the waitlist entry
            **kwargs: Additional tool-specific parameters

        Returns:
            str: Waitlist confirmation details or error message
        """
        raise NotImplementedError
