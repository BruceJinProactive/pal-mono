from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.opentable_tool._apis import (
    get_availability_metadata as get_availability_metadata_api,
)
from tools.opentable_tool._apis import get_opentable_access_token, make_reservation
from tools.opentable_tool._apis import search_availability as search_availability_api
from tools.opentable_tool._prompt_constants import (
    RESERVATION_EXTRACTOR_SYSTEM_PROMPT,
    RESERVATION_EXTRACTOR_USER_PROMPT,
)
from tools.opentable_tool._utils import (
    extract_booking_url,
    format_availability_metadata,
    format_availability_results,
    prepare_reservation_parameters,
    validate_search_parameters,
)
from tools.opentable_tool.classes import (
    AvailabilitySearchRequest,
    OpenTableAccessToken,
    ReservationExtractedData,
    TableAttribute,
)
from utils.log import logger
from utils.ordering import _llm


class OpenTableTool(Toolkit):
    # Default time window for availability search in minutes
    DEFAULT_SEARCH_FORWARD_MINUTES = 60
    DEFAULT_SEARCH_BACKWARD_MINUTES = 60

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        tool_metadata: ToolMetadata,
        use_production: bool = False,
    ):
        super().__init__(name="opentable_tool")

        self.client_id = client_id
        self.client_secret = client_secret
        self.use_production = use_production
        self.tool_metadata = tool_metadata

        # Initialize QueryMessagesTool for chat history retrieval
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

        # Register tools
        self.register(self.search_availability)
        self.register(self.get_availability_metadata)
        self.register(self.make_reservation)

    @cached_property
    def _opentable_bearer_token(self) -> OpenTableAccessToken | None:
        """Get and cache the OpenTable bearer token"""
        with LLMObs.task(name="get_opentable_bearer_token"):
            bearer_token = get_opentable_access_token(
                client_id=self.client_id,
                client_secret=self.client_secret,
                use_production=self.use_production,
            )
            if not bearer_token:
                logger.error("Failed to obtain OpenTable access token", exc_info=True)
            return bearer_token

    @tool
    def search_availability(
        self,
        restaurant_id: int,
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
            restaurant_id: The OpenTable ID (rid) of the restaurant
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
            return "Error: Unable to authenticate with OpenTable"

        # Validate restaurant_id
        if not restaurant_id or not isinstance(restaurant_id, int):
            return "Error: restaurant_id is required and must be a valid integer"

        # Validate search parameters
        is_valid, error_message, validated_params = validate_search_parameters(
            party_size=party_size,
            start_time=start_date_time,
            forward_minutes=forward_minutes,
            backward_minutes=backward_minutes,
        )

        if not is_valid:
            return f"Error: {error_message}"

        # If require_attributes is provided, validate it
        table_attribute = None
        if require_attributes:
            try:
                table_attribute = TableAttribute(require_attributes.lower())
            except ValueError:
                return f"Error: Invalid table attribute '{require_attributes}'. Valid options are: default, hightop, bar, counter, outdoor."

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
                    restaurant_id=restaurant_id,
                    search_params=search_params,
                    use_production=self.use_production,
                )
        except Exception as e:
            logger.error(f"Error searching availability: {str(e)}", exc_info=True)
            return f"Error searching availability for restaurant ID {restaurant_id}: {str(e)}"

        # If no times available, provide a clear message
        if not result.times and not result.times_available:
            no_availability_reasons = result.no_availability_reasons or []
            reasons = (
                ", ".join(reason.value for reason in no_availability_reasons)
                or "No available times"
            )
            return f"No availability found for restaurant ID {restaurant_id} (Party of {party_size}). Reason: {reasons}"

        # Format the results in a human-readable way
        formatted_result = format_availability_results(result)

        # Add booking URLs if requested
        if include_booking_urls and result.times_available:
            booking_urls = []
            for time_slot in result.times_available:
                time_str = getattr(time_slot, "time", "Unknown time")
                url = extract_booking_url(time_slot, is_affiliate)
                if url:
                    booking_urls.append(f"• {time_str}: {url}")

            if booking_urls:
                formatted_result += "\n\nBooking URLs (for direct reservation):\n"
                formatted_result += "\n".join(
                    booking_urls[:5]
                )  # Limit to 5 URLs to avoid overloading
                if len(booking_urls) > 5:
                    formatted_result += (
                        "\n(More booking URLs available - showing first 5 only)"
                    )

        return formatted_result

    @tool
    def get_availability_metadata(
        self,
        restaurant_id: int,
    ) -> str:
        """
        Get detailed availability metadata for an OpenTable restaurant.
        Returns information about dining areas, table attributes, and environments.

        Args:
            restaurant_id: The OpenTable ID (rid) of the restaurant

        Returns:
            Formatted string with restaurant availability options and attributes
        """
        # Get bearer token
        bearer_token = self._opentable_bearer_token
        if not bearer_token:
            return "Error: Unable to authenticate with OpenTable"

        # Validate restaurant_id
        if not restaurant_id or not isinstance(restaurant_id, int):
            return "Error: restaurant_id is required and must be a valid integer"

        try:
            # Get availability metadata
            with LLMObs.task(name="get_opentable_availability_metadata"):
                result = get_availability_metadata_api(
                    bearer_token=bearer_token,
                    restaurant_id=restaurant_id,
                    use_production=self.use_production,
                )
        except Exception as e:
            logger.error(
                f"Error getting availability metadata: {str(e)}", exc_info=True
            )
            return f"Error retrieving availability options for restaurant ID {restaurant_id}: {str(e)}"

        # Format the results in a human-readable way
        return format_availability_metadata(result)

    @tool
    def make_reservation(self, latest_user_message: str, restaurant_id: int) -> str:
        """
        Creates a restaurant reservation by extracting structured reservation data from chat
        history and using OpenTable tools to resolve the necessary information.
        This function should be invoked when the user asks to make a reservation,
        book a table, etc.

        Args:
            latest_user_message (str): The latest user message in the chat history.
            restaurant_id (int): The OpenTable restaurant ID (rid) for the restaurant.

        Returns:
            str: The reservation confirmation details including confirmation number and manage URL.
        """
        try:
            # Get bearer token
            bearer_token = self._opentable_bearer_token
            if not bearer_token:
                return "Error: Unable to authenticate with OpenTable"

            # Validate restaurant_id
            if not restaurant_id or not isinstance(restaurant_id, int):
                return "Error: restaurant_id is required and must be a valid integer"

            # Get chat history
            chat_history = str(
                self.query_messages_tool.query_messages(latest_user_message)  # type: ignore
            )

            # Get restaurant metadata for context
            try:
                metadata_result = get_availability_metadata_api(
                    bearer_token=bearer_token,
                    restaurant_id=restaurant_id,
                    use_production=self.use_production,
                )
                metadata_context = format_availability_metadata(metadata_result)
            except Exception as e:
                logger.debug(f"Failed to get restaurant metadata: {e}")
                return "Error: Unable to get restaurant metadata"

            # Extract reservation data using LLM
            reservation_data = _llm.llm_call(
                system_prompt=RESERVATION_EXTRACTOR_SYSTEM_PROMPT,
                prompt=RESERVATION_EXTRACTOR_USER_PROMPT.format(
                    context=metadata_context, chat_history=chat_history
                ),
                response_format=ReservationExtractedData,
                reasoning=False,
            )

            if not isinstance(reservation_data, ReservationExtractedData):
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
            if not reservation_data.first_name:
                missing_fields.append("a name for the reservation (first name)")
            if not (reservation_data.phone and reservation_data.phone.number):
                missing_fields.append("a phone number for the reservation")
            if not reservation_data.email_address:
                missing_fields.append("an email address for the reservation")

            # Check for authentication issues
            if not bearer_token.access_token:
                return "I'm having trouble authenticating with OpenTable endpoint. Please try again in a moment."

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

            # Prepare reservation parameters using utility function
            reservation_params = prepare_reservation_parameters(
                access_token=bearer_token.access_token,  # type: ignore
                restaurant_id=restaurant_id,
                party_size=reservation_data.party_size,  # type: ignore
                datetime_iso=reservation_data.date_time.isoformat(),  # type: ignore
                first_name=reservation_data.first_name,  # type: ignore
                last_name=reservation_data.last_name or "",
                email_address=reservation_data.email_address,  # type: ignore
                phone=reservation_data.phone,  # type: ignore
                reservation_attribute=(
                    reservation_data.table_preference.value
                    if reservation_data.table_preference
                    else "default"
                ),
                environment=(
                    reservation_data.environment_preference.value
                    if reservation_data.environment_preference
                    else None
                ),
                special_request=reservation_data.special_request,
                restaurant_email_marketing_opt_in=reservation_data.restaurant_email_marketing_opt_in
                or False,
                sms_notifications_opt_in=reservation_data.sms_notifications_opt_in
                or False,
                use_production=self.use_production,
            )

            # Check if prepare_reservation_parameters returned an error
            if isinstance(reservation_params, str):
                return f"Unable to make reservation: {reservation_params}"

            # Create the reservation
            with LLMObs.task(name="make_opentable_reservation"):
                reservation_result = make_reservation(**reservation_params)

            # Format successful response
            response = "Reservation confirmed!\n\n"
            response += (
                f"Confirmation Number: {reservation_result.confirmation_number}\n"
            )
            response += f"Date & Time: {reservation_result.date_time}\n"
            response += f"Party Size: {reservation_result.party_size}\n"
            response += f"Guest: {reservation_data.first_name} {reservation_data.last_name or ''}\n"

            if reservation_result.notes:
                response += f"Notes: {reservation_result.notes}\n"

            response += f"\nTo manage your reservation: {reservation_result.manage_reservation_url}\n"

            if reservation_result.message:
                response += f"\nImportant Information:\n{reservation_result.message}"

            return response

        except Exception as e:
            logger.error(f"Error in make_reservation: {str(e)}", exc_info=True)
            return "Sorry, there was an error processing your reservation request. Please try again."
