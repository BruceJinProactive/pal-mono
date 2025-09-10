import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.base.reservation import BaseReservationTool, params_validate
from tools.opentable_tool._apis import search_availability as search_availability_api
from tools.opentable_tool._utils import (
    format_availability_results,
    validate_search_parameters,
)
from tools.opentable_tool.classes import AvailabilitySearchRequest, OpenTableAccessToken
from utils.log import logger


class OpenTableTool(Toolkit, BaseReservationTool):

    # Required fields for each tool method
    REQUIRED_CHECK_AVAILABILITY_FIELDS = ["party_size", "date", "time"]
    REQUIRED_MAKE_RESERVATION_FIELDS = ["party_size", "date", "time"]

    def __init__(
        self,
        restaurant_id: int,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="opentable_tool")

        self.restaurant_id = restaurant_id
        self.tool_metadata = tool_metadata

        # Register tools
        self.register(self.check_availability)
        self.register(self.make_reservation)

    @cached_property
    def _opentable_bearer_token(self) -> OpenTableAccessToken | None:
        """Fetch CSRF token from restaurant page and wrap as access token."""
        try:
            url = f"https://www.opentable.com/restref/client/?rid={self.restaurant_id}"
            req = urllib.request.Request(url, headers={"Cookie": "OT-Locale=en-US"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8")

            match = re.search(r'"__CSRF_TOKEN__"\s*:\s*"([^"]+)"', html)
            if not match:
                logger.error("OpenTable CSRF token not found in HTML response")
                return None

            token = match.group(1)
            logger.debug("OpenTable CSRF token acquired")
            return OpenTableAccessToken(
                access_token=token, token_type="Bearer", expires_in=3600, scope=None
            )
        except Exception as e:
            logger.error(f"Error fetching OpenTable token: {str(e)}")
            return None

    def _get_fresh_token(self) -> OpenTableAccessToken | None:
        """Return a valid token, refreshing the cached one if expired (60s skew)."""
        token = self._opentable_bearer_token
        try:
            if token:
                created = token.created_at
                now = datetime.now(getattr(created, "tzinfo", None) or timezone.utc)
                if (now - created).total_seconds() > max(0, token.expires_in - 60):
                    # drop cache and reacquire
                    self.__dict__.pop("_opentable_bearer_token", None)
                    token = self._opentable_bearer_token
        except Exception:
            # Fail open; downstream handles missing/invalid token
            pass
        return token

    @tool
    @params_validate()
    def check_availability(self, party_size: int, date: str, time: str) -> str:  # type: ignore[misc]
        """
        Check availability for restaurant reservations.

        Args:
            party_size: Number of people for the reservation
            date: Date for the reservation in YYYY-MM-DD format
            time: Time for the reservation in HH:MM format (24-hour)
        Returns a formatted list of available times if found.
        """
        # Get bearer token (refresh if expired)
        bearer_token = self._get_fresh_token()
        if not bearer_token:
            logger.error(
                "[OpenTable Tool] Error: Unable to authenticate with OpenTable"
            )
            return "Error: Unable to authenticate with OpenTable"

        # Validate search parameters
        # Combine date and time into ISO format expected by OpenTable utils
        start_date_time = f"{date}T{time}"
        is_valid, error_message, validated_params = validate_search_parameters(
            party_size=party_size,
            start_time=start_date_time,
        )

        if not is_valid:
            logger.error(f"[OpenTable Tool] Error: {error_message}")
            return f"Error: {error_message}"

        # Create search parameters
        search_params = AvailabilitySearchRequest(
            start_date_time=validated_params["start_date_time"],
            party_size=validated_params["party_size"],
        )

        try:
            # Search for availability
            with LLMObs.task(name="search_opentable_availability"):
                result = search_availability_api(
                    bearer_token=bearer_token,
                    restaurant_id=self.restaurant_id,
                    search_params=search_params,
                )
                logger.info(f"[OpenTable Tool] Search availability result: {result}")
        except Exception as e:
            logger.error(
                f"[OpenTable Tool] Error searching availability: {str(e)}",
                exc_info=True,
            )
            return f"Error searching availability for restaurant ID {self.restaurant_id}: {str(e)}"

        # If no times available, provide a clear message
        if not result.times_available:
            no_availability_reasons = result.no_availability_reasons or []
            reasons = (
                ", ".join(getattr(r, "value", r) for r in no_availability_reasons)
                or "No available times"
            )
            logger.info(
                f"[OpenTable Tool] No availability found for restaurant ID {self.restaurant_id} (Party of {party_size}). Reason: {reasons}"
            )
            return f"No availability found for restaurant ID {self.restaurant_id} (Party of {party_size}). Reason: {reasons}"

        # Format the results in a human-readable way
        formatted_result = format_availability_results(result)
        logger.info(f"[OpenTable Tool] Formatted result: {formatted_result}")
        return formatted_result

    @tool
    @params_validate()
    def make_reservation(  # type: ignore[misc]
        self,
        phone: str,
        first_name: str,
        party_size: int,
        date: str,
        time: str,
        last_name: str = "",
        email: str = "",
        notes: str = "",
    ) -> str:
        """
        Make a reservation at the restaurant (via booking link).

        Notes:
            OpenTable flow completes on their website. Customer details (name, phone, email, notes)
            are not processed here and are not required by this tool. They may be ignored.

        Args:
            phone: Customer phone number (optional, ignored)
            first_name: Customer first name (optional, ignored)
            party_size: Number of people for the reservation
            date: Date for the reservation in YYYY-MM-DD format
            time: Time for the reservation in HH:MM format (24-hour)
            last_name: Customer last name (optional, ignored)
            email: Customer email address (optional, ignored)
            notes: Optional notes for the reservation (optional, ignored)

        Returns:
            str: A short summary plus a direct link to complete the reservation on OpenTable.
        """
        try:
            # Combine date/time and validate
            start_date_time = f"{date}T{time}"
            is_valid, error_message, validated = validate_search_parameters(
                party_size=party_size, start_time=start_date_time
            )
            if not is_valid:
                logger.error(
                    f"[OpenTable Tool] make_reservation validation error: {error_message}"
                )
                return f"Error: {error_message}"

            normalized_dt = validated["start_date_time"]

            # URL encode the dateTime parameter to match OpenTable's format
            encoded_date_time = urllib.parse.quote(normalized_dt)

            # Create the booking URL with the provided parameters
            booking_url = f"https://www.opentable.com/booking/details?dateTime={encoded_date_time}&partySize={party_size}&rid={self.restaurant_id}"

            # Format the response with the booking link
            response = "I've prepared your reservation request!\n\n"
            response += f"Date & Time: {normalized_dt}\n"
            response += f"Party Size: {party_size}\n"
            response += f"Restaurant ID: {self.restaurant_id}\n\n"
            response += f"Click here to complete your reservation: {booking_url}\n\n"
            response += "This link takes you to OpenTable to complete your reservation."

            return response

        except Exception as e:
            logger.error(f"Error in make_reservation: {str(e)}", exc_info=True)
            return "Sorry, there was an error processing your reservation request. Please try again."

    # The following BaseReservationTool methods are not supported by OpenTable.
    # They are implemented to conform to the interface but only return a message.

    def get_waitlist_status(self) -> str:  # type: ignore[misc]
        return "Waitlist is not supported for OpenTable."

    def join_waitlist_queue(  # type: ignore[misc]
        self,
        first_name: str,
        phone: str,
        party_size: int,
        last_name: str = "",
        notes: str = "",
    ) -> str:
        return "Joining a waitlist is not supported for OpenTable."

    def get_user_wait_status(self, phone: str) -> str:  # type: ignore[misc]
        return "User wait status is not supported for OpenTable."
