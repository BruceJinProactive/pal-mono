import urllib.error
from datetime import datetime
from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.base.reservation import BaseReservationTool, params_validate
from tools.resy_tool._client import find_resy_availability
from tools.resy_tool._utils import (
    extract_resy_availability,
    format_resy_availability,
    normalize_reservation_datetime,
)
from utils.log import logger


class ResyTool(Toolkit, BaseReservationTool):
    """Reservation assistant that surfaces Resy availability and booking links."""

    REQUIRED_CHECK_AVAILABILITY_FIELDS = ["party_size", "date", "time"]
    REQUIRED_MAKE_RESERVATION_FIELDS = ["party_size", "date", "time"]

    def __init__(
        self,
        venue_id: int,
        city: str,
        venue_name: str,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="resy_tool")

        if not venue_id:
            raise ValueError("Resy venue_id is required")
        if not city:
            raise ValueError("Resy city is required")
        if not venue_name:
            raise ValueError("Resy venue name is required")

        self.venue_id = venue_id
        self.city = city
        self.venue_name = venue_name
        self.tool_metadata = tool_metadata

        self.register(self.check_availability)
        self.register(self.make_reservation)

    @cached_property
    def booking_base_url(self) -> str:
        """Return the deep-link base for booking."""

        return f"https://resy.com/cities/{self.city}/venues/{self.venue_name}"

    def _search_resy(self, *, day: str, time_filter: str, party_size: int) -> dict:
        return find_resy_availability(
            venue_id=self.venue_id,
            city=self.city,
            venue_name=self.venue_name,
            day=day,
            party_size=party_size,
            time_filter=time_filter,
        )

    @tool
    @params_validate()
    def check_availability(self, party_size: int, date: str, time: str) -> str:  # type: ignore[misc]
        """
        Check reservation availability for the Resy venue.

        Args:
            party_size: Number of guests for the reservation.
            date: Desired reservation date in YYYY-MM-DD format.
            time: Desired reservation time in HH:MM (24-hour) format.

        Returns:
            Human-readable availability summary or an error message.
        """

        try:
            with LLMObs.task(name="search_resy_availability"):
                response = self._search_resy(
                    day=date, time_filter=time, party_size=party_size
                )
        except urllib.error.HTTPError as exc:
            body = (
                exc.read().decode("utf-8", errors="ignore")
                if hasattr(exc, "read")
                else ""
            )
            logger.error(
                "[Resy Tool] HTTP error during availability search",
                extra={"code": exc.code, "reason": exc.reason, "body": body},
            )
            return (
                f"Error searching availability for venue {self.venue_id}: "
                f"HTTP {exc.code} {exc.reason}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[Resy Tool] Unexpected error during availability search",
                exc_info=True,
            )
            return f"Error searching availability for venue {self.venue_id}: {exc}"

        slots = extract_resy_availability(response, party_size=party_size)
        if not slots:
            logger.info(
                "[Resy Tool] No availability",
                extra={"venue_id": self.venue_id, "party_size": party_size},
            )
            return f"No availability found for venue {self.venue_id} (Party of {party_size})."

        try:
            requested_dt = datetime.fromisoformat(f"{date}T{time}")
        except ValueError:
            requested_dt = None

        formatted = format_resy_availability(
            slots, party_size=party_size, requested_time=requested_dt
        )
        logger.info("[Resy Tool] Formatted availability: %s", formatted)
        return formatted

    @tool
    @params_validate()
    def make_reservation(  # type: ignore[misc]
        self,
        name: str,
        party_size: int,
        date: str,
        time: str,
        email: str = "",
        notes: str = "",
    ) -> str:
        """
        Make sure to use check_availability before making the reservation. Provides a Resy booking link for the user to reserve a slot.

        Args:
            name: Optional Guest name (ignored by this tool).
            party_size: Number of guests for the reservation.
            date: Desired reservation date in YYYY-MM-DD format.
            time: Desired reservation time in HH:MM (24-hour) format.
            email: Optional guest email (ignored by this tool).
            notes: Optional notes (ignored by this tool).

        Returns:
            String containing a summary and the Resy booking link, or an error message.
        """

        try:
            normalized_dt = normalize_reservation_datetime(date, time)
        except ValueError as exc:
            logger.error(
                "[Resy Tool] Invalid reservation datetime",
                extra={"date": date, "time": time, "error": str(exc)},
            )
            return f"Error: Invalid reservation time: {exc}"

        normalized_dt_obj = datetime.fromisoformat(normalized_dt)
        floored_minutes = normalized_dt_obj.minute - (normalized_dt_obj.minute % 30)
        floored_dt = normalized_dt_obj.replace(
            minute=floored_minutes, second=0, microsecond=0
        )
        booking_time = floored_dt.strftime("%H%M")
        booking_url = f"{self.booking_base_url}?seats={party_size}&date={date}&time={booking_time}"

        lines = [
            "Inform the user that the reservation link is available",
            f"Date & Time: {normalized_dt}",
            f"Party Size: {party_size}",
            "",
            f"Tell the user they have to click this link sent to complete their reservation: {booking_url}",
            f"This link takes the user to Resy. Inform the user that on the Resy site they will have to click the blue {time} button, then press complete reservation and then give their phone number to complete the reservation.",
        ]
        return "\n".join(lines)

    def get_waitlist_status(self) -> str:  # type: ignore[misc]
        return "Waitlist is not supported for Resy."

    def join_waitlist_queue(  # type: ignore[misc]
        self,
        name: str,
        party_size: int,
        notes: str = "",
    ) -> str:
        return "Joining a waitlist is not supported for Resy."

    def get_user_wait_status(self) -> str:  # type: ignore[misc]
        return "User wait status is not supported for Resy."
