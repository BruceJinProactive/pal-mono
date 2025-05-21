from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from tools.opentable_tool._apis import (
    get_availability_metadata,
    get_opentable_access_token,
    search_availability,
)
from tools.opentable_tool._utils import (
    extract_booking_url,
    format_availability_metadata,
    format_availability_results,
    validate_search_parameters,
)
from tools.opentable_tool.classes import (
    AvailabilitySearchRequest,
    OpenTableAccessToken,
    TableAttribute,
)
from utils.log import logger


class OpenTableTool(Toolkit):
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        use_production: bool = False,
        tool_metadata=None,
    ):
        super().__init__(name="opentable_tool")

        self.client_id = client_id
        self.client_secret = client_secret
        self.use_production = use_production
        self.tool_metadata = tool_metadata

        # Register tools
        self.register(self.search_availability)
        self.register(self.get_availability_metadata)

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
                logger.error("Failed to obtain OpenTable access token")
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

        # Validate required parameters
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
                result = search_availability(
                    bearer_token=bearer_token,
                    restaurant_id=restaurant_id,
                    search_params=search_params,
                    use_production=self.use_production,
                )

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

        except Exception as e:
            logger.error(f"Error searching OpenTable availability: {str(e)}")
            return f"Error searching for restaurant availability: {str(e)}"

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

        # Validate required parameters
        if not restaurant_id or not isinstance(restaurant_id, int):
            return "Error: restaurant_id is required and must be a valid integer"

        try:
            # Get availability metadata
            with LLMObs.task(name="get_opentable_availability_metadata"):
                result = get_availability_metadata(
                    bearer_token=bearer_token,
                    restaurant_id=restaurant_id,
                    use_production=self.use_production,
                )

            # Format the results in a human-readable way
            formatted_result = format_availability_metadata(result)
            return formatted_result

        except Exception as e:
            logger.error(f"Error getting OpenTable availability metadata: {str(e)}")
            return f"Error retrieving availability options for restaurant ID {restaurant_id}: {str(e)}"
