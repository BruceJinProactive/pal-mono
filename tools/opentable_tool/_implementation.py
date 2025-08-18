import re
import urllib.parse
import urllib.request
from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.opentable_tool._apis import search_availability as search_availability_api
from tools.opentable_tool._prompt_constants import (
    RESERVATION_EXTRACTOR_SYSTEM_PROMPT,
    RESERVATION_EXTRACTOR_USER_PROMPT,
)
from tools.opentable_tool._utils import (
    format_availability_results,
    validate_search_parameters,
)
from tools.opentable_tool.classes import (
    AvailabilitySearchRequest,
    OpenTableAccessToken,
    ReservationExtractedData,
    TableAttribute,
)
from tools.utils.ordering import _llm
from utils.log import logger


class OpenTableTool(Toolkit):
    # Default time window for availability search in minutes
    DEFAULT_SEARCH_FORWARD_MINUTES = 60
    DEFAULT_SEARCH_BACKWARD_MINUTES = 60

    def __init__(
        self,
        restaurant_id: int,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="opentable_tool")

        self.restaurant_id = restaurant_id
        self.tool_metadata = tool_metadata

        # Initialize QueryMessagesTool for chat history retrieval
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

        # Register tools
        self.register(self.search_availability)
        self.register(self.make_reservation)

    @cached_property
    def _opentable_bearer_token(self) -> OpenTableAccessToken | None:
        """Get and cache the OpenTable bearer token by fetching authToken from HTML page"""
        try:
            # Make GET request to the OpenTable restaurant page
            url = f"https://www.opentable.com/restref/client/?rid={self.restaurant_id}"
            restaurant_req = urllib.request.Request(
                url, headers={"Cookie": "OT-Locale=en-US"}
            )

            # Visit restaurant page
            with urllib.request.urlopen(restaurant_req, timeout=30) as response:
                html_content = response.read().decode("utf-8")
                logger.info("Successful fetch of OpenTable restaurant page")

            # Look for authToken in the HTML - it's typically in a script tag or data attribute
            auth_token_pattern = r'"authToken":\s*"([^"]+)"'  # Exact JSON format

            auth_token = None
            logger.info("Looking for authToken in OpenTable HTML response")
            match = re.search(auth_token_pattern, html_content)
            if match:
                auth_token = match.group(1)

            if not auth_token:
                logger.error("Could not find authToken in OpenTable HTML response")
                return None

            # Log successful token extraction (first 20 chars for debugging)
            logger.info(
                f"Successfully extracted OpenTable auth token: {auth_token[:20]}..."
            )

            # Create OpenTableAccessToken object
            return OpenTableAccessToken(
                access_token=auth_token,
                token_type="Bearer",
                expires_in=3600,  # Assume 1 hour expiration
                scope=None,
            )

        except Exception as e:
            logger.error(f"Error fetching OpenTable auth token: {str(e)}")
            return None

    @tool
    def search_availability(
        self,
        party_size: int,
        start_date_time: str | None = None,
        forward_minutes: int = 120,
        backward_minutes: int = 120,
        require_attributes: str | None = None,
        include_credit_card_results: bool | None = None,
        include_experiences: bool = False,
        include_booking_urls: bool = True,
        is_affiliate: bool = True,
    ) -> str:
        """
        Search for reservation availability at an OpenTable restaurant.
        Returns a formatted list of available times.

        Args:
            party_size: Number of people in the party
            start_date_time: The local date and time to search (ISO 8601 format, e.g. "2023-10-31T19:00")
                             Must be aligned with 15-minute intervals (00, 15, 30, 45)
                             If not provided, the current time will be used.
            forward_minutes: Minutes to search forward from start time (default: 120, max: 720)
            backward_minutes: Minutes to search backward from start time (default: 120, max: 720)
            require_attributes: Table type for search. Options: "default", "hightop", "bar", "counter", "outdoor"
                                If not specified, "default" is used.
            include_credit_card_results: When true, returns availability requiring credit card (default: None)
            include_experiences: When true, returns availability for special dining experiences (default: True)
            include_booking_urls: Whether to include booking URLs in the results (default: True)
            is_affiliate: Whether the requestor is an affiliate partner (True) or restaurant (False)
                          Determines which booking URL to return (default: True)

        Returns:
            Formatted string of available reservation times and details
        """
        # Get bearer token
        bearer_token = self._opentable_bearer_token
        if not bearer_token:
            logger.error(
                "[OpenTable Tool] Error: Unable to authenticate with OpenTable"
            )
            return "Error: Unable to authenticate with OpenTable"

        # Validate search parameters
        is_valid, error_message, validated_params = validate_search_parameters(
            party_size=party_size,
            start_time=start_date_time,
            forward_minutes=forward_minutes,
            backward_minutes=backward_minutes,
        )

        if not is_valid:
            logger.error(f"[OpenTable Tool] Error: {error_message}")
            return f"Error: {error_message}"

        # If require_attributes is provided, validate it
        table_attribute = None
        if require_attributes:
            try:
                table_attribute = TableAttribute(require_attributes.lower())
            except ValueError:
                logger.error(
                    f"[OpenTable Tool] Error: Invalid table attribute '{require_attributes}'. Valid options are: default, hightop, bar, counter, outdoor."
                )
                return f"[OpenTable Tool] Error: Invalid table attribute '{require_attributes}'. Valid options are: default, hightop, bar, counter, outdoor."

        # Create search parameters
        search_params = AvailabilitySearchRequest(
            start_date_time=validated_params["start_date_time"],
            forward_minutes=validated_params["forward_minutes"],
            backward_minutes=validated_params["backward_minutes"],
            party_size=validated_params["party_size"],
            require_attributes=table_attribute,
            include_credit_card_results=include_credit_card_results,
            include_experiences=include_experiences,
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
                ", ".join(reason.value for reason in no_availability_reasons)
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
    def make_reservation(self) -> str:
        """
        Creates a restaurant reservation by extracting structured reservation data from chat
        history and using OpenTable tools to resolve the necessary information.
        This function should be invoked when the user asks to make a reservation,
        book a table, etc.

        Args:
            None

        Returns:
            str: The reservation confirmation details including confirmation number and manage URL.
        """
        try:
            # Get bearer token
            bearer_token = self._opentable_bearer_token
            if not bearer_token:
                logger.error(
                    "[OpenTable Tool] Error: Unable to authenticate with OpenTable"
                )
                return "Error: Unable to authenticate with OpenTable"

            # Get chat history
            chat_history = str(self.query_messages_tool.query_messages())

            # Extract reservation data using LLM
            reservation_data = _llm.llm_call(
                system_prompt=RESERVATION_EXTRACTOR_SYSTEM_PROMPT,
                prompt=RESERVATION_EXTRACTOR_USER_PROMPT.format(
                    context="", chat_history=chat_history
                ),
                response_format=ReservationExtractedData,
                openai=False,
            )

            if not isinstance(reservation_data, ReservationExtractedData):
                logger.error(
                    "[OpenTable Tool] Failed to extract structured reservation data. Please try again."
                )
                return (
                    "Failed to extract structured reservation data. Please try again."
                    f"Error: {reservation_data}"
                )

            # Comprehensive validation of required fields
            missing_fields = []

            if not reservation_data.party_size:
                missing_fields.append("how many people will be dining (party size)")
            if not reservation_data.date_time:
                missing_fields.append("when you'd like to dine (date and time)")

            # Return comprehensive error message if any fields are missing
            if missing_fields:
                if len(missing_fields) == 1:
                    return f"I need to know {missing_fields[0]}. Could you please provide this information?"
                elif len(missing_fields) == 2:
                    return f"I need to know {missing_fields[0]} and {missing_fields[1]}. Could you please provide this information?"
                else:
                    formatted_fields = (
                        ", ".join(missing_fields[:-1]) + f", and {missing_fields[-1]}"
                    )
                    return f"I need to know {formatted_fields}. Could you please provide this information?"

            # Generate the direct booking link
            date_time_str = reservation_data.date_time.isoformat()  # type: ignore
            party_size = reservation_data.party_size  # type: ignore

            # URL encode the dateTime parameter to match OpenTable's format
            encoded_date_time = urllib.parse.quote(date_time_str)

            # Create the booking URL with the extracted parameters
            booking_url = f"https://www.opentable.com/booking/details?dateTime={encoded_date_time}&partySize={party_size}&rid={self.restaurant_id}"

            # Format the response with the booking link
            response = "I've prepared your reservation request!\n\n"
            response += f"Date & Time: {reservation_data.date_time}\n"  # type: ignore
            response += f"Party Size: {party_size}\n"
            response += f"Restaurant ID: {self.restaurant_id}\n\n"
            response += f"Click here to complete your reservation: {booking_url}\n\n"
            response += "This link will take you directly to OpenTable's booking page where you can complete your reservation."

            return response

        except Exception as e:
            logger.error(f"Error in make_reservation: {str(e)}", exc_info=True)
            return "Sorry, there was an error processing your reservation request. Please try again."
