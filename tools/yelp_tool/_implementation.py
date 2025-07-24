import traceback
import uuid
from datetime import datetime
from functools import cached_property
from typing import Optional
from zoneinfo import ZoneInfo

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.utils.ordering._llm import llm_call
from tools.yelp_tool._apis import (
    create_hold_creditcard_not_required,
    get_openings_creditcard_not_required,
    get_openings_creditcard_required,
    get_waitlist_status,
    get_yelp_bearer_token,
)
from tools.yelp_tool._prompt_constants import (
    OPENINGS_EXTRACTION_SYSTEM_PROMPT,
    OPENINGS_EXTRACTION_USER_PROMPT,
    RESERVATION_EXTRACTION_SYSTEM_PROMPT,
    RESERVATION_EXTRACTION_USER_PROMPT,
)
from tools.yelp_tool._utils import (
    create_holds_request_creditcard_not_required,
    create_openings_request_creditcard_not_required,
    create_openings_request_creditcard_required,
    create_reservation_from_hold_creditcard_not_required,
    create_waitlist_status_request,
    format_openings_for_llm_creditcard_not_required,
    format_openings_for_llm_creditcard_required,
    format_waitlist_status_for_llm,
    get_reservation_url_creditcard_required,
)
from tools.yelp_tool.classes import (
    OpeningsQuery,
    OpeningsQueryWithoutCreditCard,
    ReservationQuery,
    YelpAccessToken,
    YelpAccessTokenRequest,
)
from utils.log import logger
from utils.secret import get_client_secret_with_fallback


class YelpTool(Toolkit):
    def __init__(
        self,
        business_id_or_alias: str,
        tool_metadata: ToolMetadata,
        credit_card_required: bool,
        yelp_integration_api: bool = False,
        biz_id: Optional[str] = None,
        biz_lat: Optional[str] = None,
        biz_long: Optional[str] = None,
    ):
        """
        Initialize YelpTool with configurable workflow parameters.

        Args:
            business_id_or_alias: The Yelp business ID or alias
            tool_metadata: Tool metadata containing session information
                        credit_card_required: Whether this business actually requires credit card for reservations
            yelp_integration_api: Use Yelp integration API workflow (no credit card required workflow).
                                Defaults to False (uses public booking API).
            biz_id: Business-specific ID parameter (required if yelp_integration_api=True)
            biz_lat: Business latitude parameter (required if yelp_integration_api=True)
            biz_long: Business longitude parameter (required if yelp_integration_api=True)

        Raises:
            ValueError: If yelp_integration_api=False but biz_id, biz_lat, or biz_long are not provided
        """
        super().__init__(name="yelp_tool")

        self.business_id_or_alias = business_id_or_alias
        self.tool_metadata = tool_metadata

        # Set credit card requirement
        self.credit_card_required = credit_card_required

        # Determine which workflow to use
        if not yelp_integration_api:
            # Use Yelp integration API workflow (credit card required workflow)
            self.use_creditcard_workflow = True
        else:
            # Use standard booking API workflow based on credit_card_required
            self.use_creditcard_workflow = credit_card_required

        # Store the API choice for reference
        self.yelp_integration_api = yelp_integration_api

        # Validate business-specific parameters for credit card workflow
        if self.use_creditcard_workflow:
            if not biz_id or not biz_lat or not biz_long:
                missing_params = []
                if not biz_id:
                    missing_params.append("biz_id")
                if not biz_lat:
                    missing_params.append("biz_lat")
                if not biz_long:
                    missing_params.append("biz_long")
                raise ValueError(
                    f"Yelp integration API workflow needs these parameters: {', '.join(missing_params)}"
                )
            self.biz_id = biz_id
            self.biz_lat = biz_lat
            self.biz_long = biz_long
        else:
            self.biz_id = None
            self.biz_lat = None
            self.biz_long = None

        # Register appropriate tools based on workflow choice
        if self.use_creditcard_workflow:
            self.register(self.get_openings_open_api_creditcard_required)
            self.register(self.make_reservation_creditcard_required)
        else:
            self.register(self.get_restaurant_openings_creditcard_not_required)
            self.register(self.make_reservation_creditcard_not_required)
            self.register(self.get_waitlist_status)

        # Initialize query messages tool
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)
        logger.debug(
            f"YelpTool instance created: business id={self.business_id_or_alias}, credit_card_required={self.credit_card_required}, yelp_integration_api={self.yelp_integration_api}, use_creditcard_workflow={self.use_creditcard_workflow}"
        )

    def _get_current_date(self) -> str:
        """
        Get the current date in YYYY-MM-DD format based on the timezone from metadata.

        Returns:
            str: Current date in YYYY-MM-DD format

        Raises:
            ValueError: If current date cannot be determined due to invalid timezone
        """
        try:
            # Determine timezone with fallback to UTC
            timezone_str = None

            if self.tool_metadata and self.tool_metadata.timezone:
                timezone_str = self.tool_metadata.timezone
            else:
                # Fallback to UTC if timezone is not available
                timezone_str = "UTC"
                logger.warning(
                    "[YelpTool._get_current_date] No timezone available in tool metadata, using UTC as fallback"
                )

            timezone = ZoneInfo(timezone_str)
            current_date = datetime.now(timezone).strftime("%Y-%m-%d")

            return current_date
        except Exception as e:
            logger.error(f"Error getting timezone-aware date: {e}")
            raise ValueError(f"Cannot determine current date. Error: {e}") from e

    @cached_property
    def _yelp_bearer_token(self) -> YelpAccessToken:
        client_id = get_client_secret_with_fallback("YELP_CLIENT_ID")
        client_secret = get_client_secret_with_fallback("YELP_CLIENT_SECRET")

        bearer_token = get_yelp_bearer_token(
            request_params=YelpAccessTokenRequest(
                client_id=client_id,
                client_secret=client_secret,
                code="PLACEHOLDER",
                grant_type="PLACEHOLDER",
            )
        )

        if not bearer_token:
            raise Exception("Failed to obtain Yelp access token")

        return YelpAccessToken(**bearer_token.model_dump())

    @retrieval
    def _get_chat_history(self, latest_user_message: str) -> str:
        """
        Retrieves the chat history from the query messages tool.

        Args:
            latest_user_message (str): The latest user message to include in the chat history.

        Returns:
            str: A string representing the entire chat history.
        """
        try:
            chat_history = self.query_messages_tool.query_messages(latest_user_message)  # type: ignore
        except Exception as e:
            logger.warning(
                f"[YelpTool._get_chat_history] Exception calling query_messages: {e}"
            )
            return latest_user_message  # sensible fallback

        if not chat_history:
            logger.warning("[YelpTool._get_chat_history] Empty chat history returned")
            return latest_user_message  # sensible fallback

        # ensure string
        if not isinstance(chat_history, str):
            chat_history = str(chat_history)

        # Basic check for error messages (TEMPORARY workaround)
        error_indicators = [
            "Error in getting chat history",
            "Conversation history not found",
            "Agent session not found",
        ]
        if any(indicator in chat_history for indicator in error_indicators):
            logger.warning(
                f"[YelpTool._get_chat_history] Possible issue with chat history: {chat_history}"
            )

        LLMObs.annotate(output_data=chat_history)
        return chat_history

    @tool
    def get_restaurant_openings_creditcard_not_required(
        self, latest_user_message: str
    ) -> str:
        """
        Get available reservation times for a restaurant using the Yelp Bookings API.

        Use when: User wants to check availability or see time options before booking.

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: Formatted string containing available reservation times, or error message
        """
        try:
            bearer_token = self._yelp_bearer_token

            # Get chat history and extract search parameters
            chat_history = self._get_chat_history(latest_user_message)  # type: ignore

            # Extract using OpeningsQuery class
            current_date = self._get_current_date()
            openings_query = llm_call(
                system_prompt=OPENINGS_EXTRACTION_SYSTEM_PROMPT.format(
                    current_date=current_date
                ),
                prompt=OPENINGS_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=OpeningsQueryWithoutCreditCard,
                reasoning=False,
            )

            if not isinstance(openings_query, OpeningsQueryWithoutCreditCard):
                return "I couldn't understand your reservation search request. Please specify the number of people, date, and time you'd like to search for."

            # Validate required fields
            if (
                not openings_query.covers
                or not openings_query.date
                or not openings_query.time
            ):
                missing_fields = []
                if not openings_query.covers:
                    missing_fields.append("number of people")
                if not openings_query.date:
                    missing_fields.append("date")
                if not openings_query.time:
                    missing_fields.append("time")

                return f"To search for available times, I need the following information: {', '.join(missing_fields)}. Please provide these details."

            success, message, request_obj = (
                create_openings_request_creditcard_not_required(
                    business_id_or_alias=self.business_id_or_alias,
                    covers=openings_query.covers,
                    date=openings_query.date,
                    time=openings_query.time,
                    get_covers_range=openings_query.get_covers_range,
                )
            )

            if not success or not request_obj:
                return f"Invalid request parameters: {message}"

            response = get_openings_creditcard_not_required(
                bearer_token=bearer_token,
                request_params=request_obj,
            )

            formatted_response = format_openings_for_llm_creditcard_not_required(
                response
            )
            return formatted_response

        except Exception as e:
            logger.debug(
                f"[YelpTool.get_restaurant_openings] Error getting openings: {e}"
            )
            logger.debug(traceback.format_exc())
            return "Failed to get restaurant openings. Please try again."

    @tool
    def make_reservation_creditcard_not_required(self, latest_user_message: str) -> str:
        """
        Make a reservation for a restaurant using the Yelp Bookings API.

        Use when: User explicitly wants to book/place/make a reservation with all required details.
        Required info: number of people, date, time, first name, last name, phone, email.

        Do NOT use for:
        - Checking availability or time slots (use get_restaurant_openings instead)
        - Getting restaurant information
        - Asking about wait times (use get_waitlist_status instead)
        - Just browsing or inquiring about reservations

        This tool will either:
        1. Complete the reservation immediately (no credit card required)
        2. Return a link to complete on Yelp's site (credit card required)
        """
        try:
            bearer_token = self._yelp_bearer_token
            if not bearer_token:
                return "Unable to authenticate with Yelp. Please try again later."

            # Extract reservation details
            chat_history = self._get_chat_history(latest_user_message)  # type: ignore
            current_date = self._get_current_date()
            reservation_query = llm_call(
                system_prompt=RESERVATION_EXTRACTION_SYSTEM_PROMPT.format(
                    current_date=current_date
                ),
                prompt=RESERVATION_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=ReservationQuery,
                reasoning=False,
            )

            if not isinstance(reservation_query, ReservationQuery):
                return "I couldn't understand your reservation request. Please provide all the necessary details."

            # Check required fields individually
            missing_fields = []
            if not reservation_query.covers:
                missing_fields.append("number of people")
            if not reservation_query.date:
                missing_fields.append("date")
            if not reservation_query.time:
                missing_fields.append("time")
            if not reservation_query.first_name:
                missing_fields.append("first name")
            if not reservation_query.last_name:
                missing_fields.append("last name")
            if not reservation_query.phone:
                missing_fields.append("phone")
            if not reservation_query.email:
                missing_fields.append("email")

            if missing_fields:
                if len(missing_fields) == 1:
                    return f"I need your {missing_fields[0]}."
                elif len(missing_fields) == 2:
                    return f"I need your {missing_fields[0]} and {missing_fields[1]}."
                else:
                    return f"I need your {', '.join(missing_fields[:-1])}, and {missing_fields[-1]}."

            # Create hold
            hold_success, hold_message, hold_request = (
                create_holds_request_creditcard_not_required(
                    business_id_or_alias=self.business_id_or_alias,
                    covers=reservation_query.covers,  # type: ignore
                    date=reservation_query.date,  # type: ignore
                    time=reservation_query.time,  # type: ignore
                    unique_id=str(uuid.uuid4()),
                )
            )

            if not hold_success or not hold_request:
                return f"Failed to create hold: {hold_message}"

            try:
                hold_response = create_hold_creditcard_not_required(
                    bearer_token=bearer_token, request_params=hold_request
                )
                if not hold_response or not hold_response.hold_id:
                    return "Unable to place a hold. Please try again."

            except Exception as e:
                error_msg = str(e).lower()

                # Determine error prefix and try to show available options
                if "covers_value_out_of_range" in error_msg:
                    error_prefix = f"This restaurant doesn't accept reservations for {reservation_query.covers} people."
                elif "invalid_date_time_range" in error_msg:
                    error_prefix = f"The date/time {reservation_query.date} at {reservation_query.time} is invalid."
                else:
                    return f"Unable to place a hold for {reservation_query.time} on {reservation_query.date} due to {error_msg}"

                # Return simple error message
                return error_prefix

            # If credit card required, return URL
            if hold_response.credit_card_hold:
                if not hold_response.reserve_url:
                    return "This restaurant requires a credit card, but the booking link is not available."

                return f"I've placed a hold for {reservation_query.covers} people on {reservation_query.date} at {reservation_query.time}.\n\nThis restaurant requires a credit card to complete the reservation.\n\nPlease complete your reservation here: {hold_response.reserve_url}\n\nNote: This hold expires in 5 minutes."

            # Create reservation directly
            reservation_success, reservation_message, reservation_response = (
                create_reservation_from_hold_creditcard_not_required(
                    bearer_token=bearer_token,
                    holds_response=hold_response,
                    holds_request=hold_request,
                    first_name=reservation_query.first_name,  # type: ignore
                    last_name=reservation_query.last_name,  # type: ignore
                    phone=reservation_query.phone,  # type: ignore
                    email=reservation_query.email,  # type: ignore
                    notes=reservation_query.notes,
                )
            )

            if not reservation_success or not reservation_response:
                return f"Failed to create reservation: {reservation_message}"

            return f"Reservation confirmed! Your reservation ID is: {reservation_response.reservation_id}"

        except Exception as e:
            logger.debug(f"[YelpTool.make_reservation] Error: {e}")
            logger.debug(traceback.format_exc())
            return "Failed to make reservation. Please try again."

    @tool
    def get_waitlist_status(self) -> str:
        """
        Get waitlist status for a restaurant using the Yelp Waitlist API.

        Use when: User asks about wait times or walk-in availability.
        Do NOT use for: Making reservations or checking reservation times.

        Returns:
            str: Formatted string containing waitlist status information, or error message
        """
        try:
            bearer_token = self._yelp_bearer_token

            # Validate bearer token before proceeding
            if not bearer_token:
                logger.debug(
                    "[YelpTool.get_waitlist_status] Failed to obtain Yelp bearer token"
                )
                return "Unable to authenticate with Yelp. Please try again later."

            # Create waitlist status request
            success, message, request_obj = create_waitlist_status_request(
                business_id_or_alias=self.business_id_or_alias,
            )

            if not success or not request_obj:
                return f"Invalid request parameters: {message}"

            # Get waitlist status from Yelp API
            response = get_waitlist_status(
                bearer_token=bearer_token,
                request_params=request_obj,
            )

            # Format and return the waitlist status information
            formatted_response = format_waitlist_status_for_llm(response)
            return formatted_response

        except Exception as e:
            logger.debug(
                f"[YelpTool.get_waitlist_status] Error getting waitlist status: {e}"
            )
            logger.debug(traceback.format_exc())
            return "Failed to get waitlist status. Please try again."

    @tool
    def get_openings_open_api_creditcard_required(
        self, latest_user_message: str
    ) -> str:
        """
        Get available reservation times for restaurants using their open API search endpoint.

        Use when: User wants to check availability or see time options for open API restaurants.

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: Formatted string containing available reservation times, or error message
        """
        try:
            # Get chat history and extract search parameters
            chat_history = self._get_chat_history(latest_user_message)  # type: ignore

            # Extract using OpeningsQuery class
            current_date = self._get_current_date()
            openings_query = llm_call(
                system_prompt=OPENINGS_EXTRACTION_SYSTEM_PROMPT.format(
                    current_date=current_date
                ),
                prompt=OPENINGS_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=OpeningsQuery,
                reasoning=False,
            )

            if not isinstance(openings_query, OpeningsQuery):
                return "I couldn't understand your reservation search request. Please specify the number of people, date, and time you'd like to search for."

            # Validate required fields
            if (
                not openings_query.covers
                or not openings_query.date
                or not openings_query.time
            ):
                missing_fields = []
                if not openings_query.covers:
                    missing_fields.append("number of people")
                if not openings_query.date:
                    missing_fields.append("date")
                if not openings_query.time:
                    missing_fields.append("time")

                return f"To search for available times, I need the following information: {', '.join(missing_fields)}. Please provide these details."

            # Create request object
            success, message, request_obj = create_openings_request_creditcard_required(
                business_id_or_alias=self.business_id_or_alias,
                covers=openings_query.covers,  # type: ignore
                date=openings_query.date,  # type: ignore
                time=openings_query.time,  # type: ignore
                biz_id=self.biz_id,  # type: ignore
                biz_lat=self.biz_lat,  # type: ignore
                biz_long=self.biz_long,  # type: ignore
                num_results_after=(0 if openings_query.before else None),
                num_results_before=(0 if openings_query.after else None),
            )

            if not success or not request_obj:
                return f"Invalid request parameters: {message}"

            # Make API call
            response = get_openings_creditcard_required(
                business_id_or_alias=self.business_id_or_alias,
                request_params=request_obj,
            )

            # Format response for display
            formatted_response = format_openings_for_llm_creditcard_required(response)
            return formatted_response

        except Exception as e:
            logger.debug(f"[YelpTool.get_openings_open_api] Error: {e}")
            logger.debug(traceback.format_exc())
            return "Failed to get restaurant openings. Please try again."

    @tool
    def make_reservation_creditcard_required(self, latest_user_message: str) -> str:
        """
        Make a reservation for restaurants using their open API workflow.

        Use when: User explicitly wants to book/place/make a reservation at open API restaurants.
        Required info: number of people, date, time.

        This will return a link to complete the reservation on Yelp's site.
        """
        try:
            # Get chat history and extract search parameters
            chat_history = self._get_chat_history(latest_user_message)  # type: ignore

            # Extract using OpeningsQuery class for basic parameters
            current_date = self._get_current_date()
            openings_query = llm_call(
                system_prompt=OPENINGS_EXTRACTION_SYSTEM_PROMPT.format(
                    current_date=current_date
                ),
                prompt=OPENINGS_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=OpeningsQuery,
                reasoning=False,
            )

            if not isinstance(openings_query, OpeningsQuery):
                return "I couldn't understand your reservation request. Please specify the number of people, date, and time you'd like to book."

            # Validate required fields
            if (
                not openings_query.covers
                or not openings_query.date
                or not openings_query.time
            ):
                missing_fields = []
                if not openings_query.covers:
                    missing_fields.append("number of people")
                if not openings_query.date:
                    missing_fields.append("date")
                if not openings_query.time:
                    missing_fields.append("time")

                return f"To make a reservation, I need the following information: {', '.join(missing_fields)}. Please provide these details."

            # Create request object
            success, message, request_obj = create_openings_request_creditcard_required(
                business_id_or_alias=self.business_id_or_alias,
                covers=openings_query.covers,  # type: ignore
                date=openings_query.date,  # type: ignore
                time=openings_query.time,  # type: ignore
                biz_id=self.biz_id,  # type: ignore
                biz_lat=self.biz_lat,  # type: ignore
                biz_long=self.biz_long,  # type: ignore
                num_results_after=(0 if openings_query.before else None),
                num_results_before=(0 if openings_query.after else None),
            )

            if not success or not request_obj:
                return f"Invalid request parameters: {message}"

            # Get availability data
            response = get_openings_creditcard_required(
                business_id_or_alias=self.business_id_or_alias,
                request_params=request_obj,
            )

            # Extract reservation URL
            url_success, url_message, reservation_url = (
                get_reservation_url_creditcard_required(response)
            )

            if not url_success or not reservation_url:
                return url_message

            return f"I found availability for {openings_query.covers} people on {openings_query.date}.\n\nThe closest available time is {response.closest_match.formatted_time if response.closest_match else 'N/A'}.\n\nPlease complete your reservation through this link: {reservation_url}"

        except Exception as e:
            logger.debug(f"[YelpTool.make_reservation_open_api] Error: {e}")
            logger.debug(traceback.format_exc())
            return "Failed to make reservation. Please try again."
