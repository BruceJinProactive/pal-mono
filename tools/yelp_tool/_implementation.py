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
from tools.yelp_tool._apis import cancel_visit as api_cancel_visit
from tools.yelp_tool._apis import (
    create_hold_creditcard_not_required,
    create_waitlist_on_my_way,
    get_openings_creditcard_not_required,
    get_openings_creditcard_required,
    get_waitlist_info,
    get_waitlist_status,
)
from tools.yelp_tool._apis import join_waitlist_queue as api_join_waitlist_queue
from tools.yelp_tool._prompt_constants import (
    CANCEL_VISIT_EXTRACTION_SYSTEM_PROMPT,
    CANCEL_VISIT_EXTRACTION_USER_PROMPT,
    OPENINGS_EXTRACTION_SYSTEM_PROMPT,
    OPENINGS_EXTRACTION_USER_PROMPT,
    RESERVATION_EXTRACTION_SYSTEM_PROMPT,
    RESERVATION_EXTRACTION_USER_PROMPT,
    WAITLIST_JOIN_QUEUE_EXTRACTION_SYSTEM_PROMPT,
    WAITLIST_JOIN_QUEUE_EXTRACTION_USER_PROMPT,
    WAITLIST_ON_MY_WAY_EXTRACTION_SYSTEM_PROMPT,
    WAITLIST_ON_MY_WAY_EXTRACTION_USER_PROMPT,
    WEEKDAY_CONVERSION_RULES,
)
from tools.yelp_tool._utils import (
    check_cancel_visit_required_fields,
    check_waitlist_join_queue_required_fields,
    check_waitlist_on_my_way_required_fields,
    create_cancel_visit_request,
    create_holds_request_creditcard_not_required,
    create_openings_request_creditcard_not_required,
    create_openings_request_creditcard_required,
    create_reservation_from_hold_creditcard_not_required,
    create_waitlist_info_request,
    create_waitlist_join_queue_request,
    create_waitlist_on_my_way_request,
    create_waitlist_status_request,
    format_cancel_visit_response_for_llm,
    format_openings_for_llm_creditcard_not_required,
    format_openings_for_llm_creditcard_required,
    format_waitlist_info_for_llm,
    format_waitlist_join_queue_response_for_llm,
    format_waitlist_on_my_way_response_for_llm,
    format_waitlist_status_for_llm,
)
from tools.yelp_tool.classes import (
    CancelVisitQuery,
    OpeningsQuery,
    OpeningsQueryWithoutCreditCard,
    ReservationQuery,
    WaitlistJoinQueueQuery,
    WaitlistOnMyWayQuery,
    YelpAccessToken,
)
from utils.log import logger
from utils.secret import get_client_secret_with_fallback


class YelpTool(Toolkit):
    def __init__(
        self,
        business_id_or_alias: str,
        tool_metadata: ToolMetadata,
        credit_card_required: bool = False,
        yelp_integration_api: bool = True,
        biz_id: Optional[str] = None,
        biz_lat: Optional[str] = None,
        biz_long: Optional[str] = None,
        waitlist_enabled: bool = False,
        reservation_enabled: bool = True,
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

        # Initialize timezone info once during tool creation
        if self.tool_metadata.timezone:
            try:
                self.timezone_info = ZoneInfo(self.tool_metadata.timezone)
            except Exception:
                # If timezone is invalid, fall back to UTC
                self.timezone_info = ZoneInfo("UTC")
                logger.warning(
                    f"[YelpTool.__init__] Invalid timezone '{self.tool_metadata.timezone}', falling back to UTC"
                )
        else:
            # If no timezone provided, fall back to UTC
            self.timezone_info = ZoneInfo("UTC")
            logger.warning(
                "[YelpTool.__init__] No timezone available in tool metadata, using UTC as fallback"
            )

        # Determine workflow: use credit card workflow if required OR if not using integration API
        self.use_creditcard_workflow = credit_card_required or not yelp_integration_api

        # Register reservation tools
        if reservation_enabled:
            # Set business parameters based on workflow (only needed for reservations)
            if self.use_creditcard_workflow:
                # Validate required parameters for credit card workflow
                missing_params = [
                    param
                    for param, value in [
                        ("biz_id", biz_id),
                        ("biz_lat", biz_lat),
                        ("biz_long", biz_long),
                    ]
                    if not value
                ]
                if missing_params:
                    raise ValueError(
                        f"Credit card workflow requires: {', '.join(missing_params)}"
                    )

                self.biz_id = biz_id
                self.biz_lat = biz_lat
                self.biz_long = biz_long

                # Register credit card workflow tools
                self.register(self.get_openings_open_api_creditcard_required)
                self.register(self.make_reservation_creditcard_required)
            else:
                # Non-credit card workflow doesn't need business parameters
                self.biz_id = None
                self.biz_lat = None
                self.biz_long = None

                # Register non-credit card workflow tools
                self.register(self.get_restaurant_openings_creditcard_not_required)
                self.register(self.make_reservation_creditcard_not_required)
        else:
            # No reservations enabled - set business parameters to None
            self.biz_id = None
            self.biz_lat = None
            self.biz_long = None

        # Register waitlist tools (independent of credit card workflow)

        if waitlist_enabled:
            # self.register(self.create_waitlist_on_my_way_visit)
            self.register(self.get_waitlist_status)
            self.register(self.get_waitlist_info)
            self.register(self.join_waitlist_queue)
            self.register(self.cancel_visit)

        # Initialize query messages tool
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)
        logger.debug(
            f"YelpTool instance created: business id={self.business_id_or_alias}, credit_card_required={credit_card_required}, yelp_integration_api={yelp_integration_api}, use_creditcard_workflow={self.use_creditcard_workflow}, waitlist_enabled={waitlist_enabled}, reservation_enabled={reservation_enabled}"
        )

    def _get_current_date(self) -> str:
        """
        Get the current date and weekday based on the timezone from metadata.

        Returns:
            str: Current date in "YYYY-MM-DD (Weekday)" format (e.g., "2024-12-18 (Wednesday)")

        Raises:
            ValueError: If current date cannot be determined due to invalid timezone
        """
        try:
            now = datetime.now(self.timezone_info)
            current_date = now.strftime("%Y-%m-%d (%A)")

            return current_date
        except Exception as e:
            logger.error(f"Error getting timezone-aware date: {e}")
            raise ValueError(f"Cannot determine current date. Error: {e}") from e

    @cached_property
    def _yelp_bearer_token(self) -> YelpAccessToken:
        api_key = get_client_secret_with_fallback("YELP_API_KEY")

        if not api_key:
            raise Exception("Failed to obtain Yelp API key")

        return YelpAccessToken(access_token=api_key, token_type="Bearer")

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
                    current_date=current_date,
                    weekday_conversion_rules=WEEKDAY_CONVERSION_RULES.format(
                        current_date=current_date
                    ),
                ),
                prompt=OPENINGS_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=OpeningsQueryWithoutCreditCard,
                openai=True,
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
        Make a restaurant reservation using the Yelp Bookings API for restaurants that support
        instant confirmation without requiring credit card validation.

        **When to use this tool:**
        - User explicitly requests to book/place/make a reservation (e.g., "Book a table", "Make a reservation", "Reserve a table for tonight")
        - User has provided or confirms all required reservation details

        **Required fields to collect before using this tool:**
        - Party size (number of people): e.g., "2", "4 people", "party of 6"
        - Date: e.g., "today", "tomorrow", "Friday", "December 15th", "2024-03-15"
        - Time: e.g., "7 PM", "19:30", "7:30 PM", or meal period ("breakfast" → 8 AM, "lunch" → 12 PM, "dinner" → 6 PM, do not ask users to specify the time again if the users use meal time to book a table, just use the estimated time of the meal period)
        - First name: Customer's first name for the reservation
        - Last name: Customer's last name for the reservation
        - Phone number: Valid phone number with area code (e.g., "555-123-4567")
        - Email address: Valid email address (e.g., "customer@email.com")

        **Optional fields:**
        - Special requests/notes: Dietary restrictions, seating preferences, etc.

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: Reservation confirmation details with confirmation number, or secure booking link
                 if credit card is required, or error message if reservation fails.
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
                    current_date=current_date,
                    weekday_conversion_rules=WEEKDAY_CONVERSION_RULES.format(
                        current_date=current_date
                    ),
                ),
                prompt=RESERVATION_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=ReservationQuery,
                openai=True,
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

                return f"I've placed a hold for {reservation_query.covers} people on {reservation_query.date} at {reservation_query.time}.\n\nThis restaurant requires a credit card to complete the reservation.\n\nPlease complete your reservation here: {hold_response.reserve_url}\n\nNote: This hold expires in 5 minutes.\n\nYou MUST include the EXACT reservation url in your response:\n{hold_response.reserve_url}"

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

            return f"Reservation confirmed! Here is the reservation details: {reservation_response}"

        except Exception as e:
            logger.debug(f"[YelpTool.make_reservation] Error: {e}")
            logger.debug(traceback.format_exc())
            return "Failed to make reservation. Please try again."

    @tool
    def get_waitlist_status(self) -> str:
        """
        Get current waitlist status and wait times for a restaurant using the Yelp Waitlist API.
        This endpoint returns real-time waitlist status including current wait estimates by party size,
        waitlist state (OPEN/ON_MY_WAY/CLOSED), and closure reasons if the waitlist is closed.

        Use when: User asks about:
        - Current wait times at the restaurant ("How long is the wait?", "What's the current wait time?")
        - Whether the restaurant currently has a wait ("Is there a wait right now?")
        - How long they'll have to wait for their party size ("How long for a party of 4?")
        - If the restaurant is accepting waitlist entries ("Can I join the waitlist?")
        - Why the waitlist might be closed ("Why can't I join the waitlist?")
        - Current waitlist state or status

        Do NOT use for:
        - Restaurant waitlist configuration/settings (use get_waitlist_info instead)
        - Joining the waitlist (use join_waitlist_queue)
        - General restaurant information

        Returns:
            str: Current waitlist state (OPEN/ON_MY_WAY/CLOSED), wait estimates by party size,
                 closure reasons if applicable, or error message
        """
        try:
            bearer_token = self._yelp_bearer_token

            # Validate bearer token before proceeding
            if not bearer_token:
                logger.debug(
                    "[YelpTool.get_waitlist_status] Failed to obtain Yelp bearer token"
                )
                return "Unable to authenticate with Yelp. Please verify your API credentials."

            # Create waitlist status request
            success, message, request_obj = create_waitlist_status_request(
                business_id_or_alias=self.business_id_or_alias,
            )

            if not success or not request_obj:
                logger.debug(
                    f"[YelpTool.get_waitlist_status] Request validation failed: {message}"
                )
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
            logger.debug(f"[YelpTool.get_waitlist_status] Error: {str(e).lower()}")
            logger.debug(traceback.format_exc())
            return "Failed to get waitlist status. Please try again."

    @tool
    def get_waitlist_info(self) -> str:
        """
        This endpoint returns waitlist configuration fields including operational parameters and
        available options for customers. This is static configuration data, not real-time status.

        Use when: User asks about:
        - Maximum party size allowed on waitlist ("What's the largest party size you accept?")
        - Available seating area options ("What seating areas can I choose from?", "Do you have patio seating?")
        - Join radius requirements ("How close do I need to be to join the waitlist?")
        - Waitlist configuration or settings ("What are your waitlist options?")
        - Whether specific seating areas are supported ("Do you have bar seating available?")
        - Waitlist operational parameters and capabilities

        Do NOT use for:
        - Current wait times or real-time status (use get_waitlist_status instead)
        - Joining the waitlist (use join_waitlist_queue)
        - Checking if there's currently a wait (use get_waitlist_status instead)

        Returns:
            str: Waitlist configuration including join radius, maximum party size, and available seating areas, or error message
        """
        try:
            bearer_token = self._yelp_bearer_token

            # Validate bearer token before proceeding
            if not bearer_token:
                logger.debug(
                    "[YelpTool.get_waitlist_info] Failed to obtain Yelp bearer token"
                )
                return "Unable to authenticate with Yelp. Please verify your API credentials."

            # Create waitlist info request
            success, message, request_obj = create_waitlist_info_request(
                business_id_or_alias=self.business_id_or_alias,
            )

            if not success or not request_obj:
                logger.debug(
                    f"[YelpTool.get_waitlist_info] Request validation failed: {message}"
                )
                return f"Invalid request parameters: {message}"

            # Get waitlist info from Yelp API
            response = get_waitlist_info(
                bearer_token=bearer_token,
                request_params=request_obj,
            )

            # Format and return the waitlist configuration information
            formatted_response = format_waitlist_info_for_llm(response)
            return formatted_response

        except Exception as e:
            logger.debug(f"[YelpTool.get_waitlist_info] Error: {str(e).lower()}")
            logger.debug(traceback.format_exc())
            return "Failed to get waitlist configuration. Please try again."

    @tool
    def create_waitlist_on_my_way_visit(self, latest_user_message: str) -> str:
        """
        Create a waitlist on-my-way visit at a restaurant using the Yelp Waitlist API.

        Use when: User wants to join the waitlist and indicates they are coming/on their way to the restaurant.

        This allows customers to notify the restaurant that they are coming and will arrive within
        a specific time window (1-30 minutes). This helps restaurants manage their waitlist more effectively.

        Required information to collect before using this tool: name, phone, party size, and estimated arrival time range (both min and max, 1-30 minutes).

        Do NOT use for:
        - Making reservations (use make_reservation instead)
        - Checking wait times (use get_waitlist_status instead)
        - Getting restaurant information
        - Just browsing or inquiring about waitlist

        Note: This endpoint requires the caller to be an onboarded Yelp Waitlist partner.

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: Confirmation of waitlist on-my-way visit creation with visit details, or error message
        """
        try:
            bearer_token = self._yelp_bearer_token

            # Validate bearer token before proceeding
            if not bearer_token:
                logger.debug(
                    "[YelpTool.create_waitlist_on_my_way_visit] Failed to obtain Yelp bearer token"
                )
                return "Unable to authenticate with Yelp. Please verify your API credentials."

            # Get chat history and extract waitlist parameters
            chat_history = self._get_chat_history(latest_user_message)  # type: ignore

            # Extract using WaitlistOnMyWayQuery class
            waitlist_query = llm_call(
                system_prompt=WAITLIST_ON_MY_WAY_EXTRACTION_SYSTEM_PROMPT,
                prompt=WAITLIST_ON_MY_WAY_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=WaitlistOnMyWayQuery,
                openai=True,
            )

            if not isinstance(waitlist_query, WaitlistOnMyWayQuery):
                return "I couldn't understand your waitlist request. Please provide your name, phone number, party size, and expected arrival time."

            # Check for required fields and provide specific feedback
            all_present, missing_prompts = check_waitlist_on_my_way_required_fields(
                business_id=self.business_id_or_alias,
                phone=waitlist_query.phone,
                party_size=waitlist_query.party_size,
                name=waitlist_query.name,
                arrival_range_max=waitlist_query.arrival_range_max,
                arrival_range_min=waitlist_query.arrival_range_min,
            )

            if not all_present:
                # Filter out business_id from user-facing messages
                user_prompts = [
                    prompt for prompt in missing_prompts if prompt != "business_id"
                ]
                if len(user_prompts) == 1:
                    return user_prompts[0]
                elif len(user_prompts) == 2:
                    return f"{user_prompts[0]} Also, {user_prompts[1].lower()}"
                else:
                    return f"{'. '.join(user_prompts[:-1])}. Also, {user_prompts[-1].lower()}"

            # Create waitlist on-my-way request
            success, message, request_obj = create_waitlist_on_my_way_request(
                business_id=self.business_id_or_alias,
                phone=waitlist_query.phone,  # type: ignore
                party_size=waitlist_query.party_size,  # type: ignore
                name=waitlist_query.name,  # type: ignore
                arrival_range_max=waitlist_query.arrival_range_max,  # type: ignore
                arrival_range_min=waitlist_query.arrival_range_min,  # type: ignore
                party_notes=waitlist_query.party_notes,
            )

            if not success or not request_obj:
                logger.debug(
                    f"[YelpTool.create_waitlist_on_my_way_visit] Request validation failed: {message}"
                )
                return f"Invalid request parameters: {message}"

            # Make API call to create waitlist on-my-way visit
            response = create_waitlist_on_my_way(
                bearer_token=bearer_token,
                request_params=request_obj,
            )

            # Format and return the success response
            formatted_response = format_waitlist_on_my_way_response_for_llm(
                response,
                timezone_info=self.timezone_info,
            )
            return formatted_response

        except Exception as e:
            logger.debug(f"[YelpTool.create_waitlist_on_my_way_visit] Error: {str(e)}")
            logger.debug(traceback.format_exc())

            return f"Failed to create waitlist on-my-way visit. {str(e)}"

    @tool
    def join_waitlist_queue(self, latest_user_message: str) -> str:
        """
        Join the waitlist queue for a restaurant using the Yelp Waitlist API.

        Use when: User asks to:
        - Join the waitlist queue ("Put me on the waitlist", "Add me to the waitlist")
        - Get in line at a restaurant ("Can I get in line?", "I want to join the queue")
        - Add their party to the wait ("Put us on the list for a table")
        - Join the wait when they know there's currently a wait time

        Required fields to collect before using this tool: name, phone, party size

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: Confirmation of waitlist queue join with visit details, expected seating times,
                 and arrival instructions, or user-friendly error message
        """
        try:
            logger.debug(
                "[YelpTool.join_waitlist_queue] Starting waitlist queue join request"
            )
            bearer_token = self._yelp_bearer_token

            # Validate bearer token before proceeding
            if not bearer_token:
                logger.debug(
                    "[YelpTool.join_waitlist_queue] Failed to obtain Yelp bearer token"
                )
                return "Unable to authenticate with Yelp. Please verify your API credentials."

            # Get chat history and extract waitlist parameters
            chat_history = self._get_chat_history(latest_user_message)  # type: ignore

            # Extract using WaitlistJoinQueueQuery class
            logger.debug(
                "[YelpTool.join_waitlist_queue] Extracting waitlist parameters using LLM"
            )
            waitlist_query = llm_call(
                system_prompt=WAITLIST_JOIN_QUEUE_EXTRACTION_SYSTEM_PROMPT,
                prompt=WAITLIST_JOIN_QUEUE_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=WaitlistJoinQueueQuery,
                openai=True,
            )

            if not isinstance(waitlist_query, WaitlistJoinQueueQuery):
                logger.debug(
                    f"[YelpTool.join_waitlist_queue] LLM extraction failed - invalid response type: {type(waitlist_query)}"
                )
                return "I couldn't understand your waitlist request. Please provide your name, phone number, and party size to join the queue."

            logger.debug(
                f"[YelpTool.join_waitlist_queue] Extracted parameters - name: {waitlist_query.name}, phone: {waitlist_query.phone}, party_size: {waitlist_query.party_size}, party_notes: {waitlist_query.party_notes}"
            )

            # Check for required fields and provide specific feedback
            logger.debug("[YelpTool.join_waitlist_queue] Validating required fields")
            all_present, missing_prompts = check_waitlist_join_queue_required_fields(
                business_id=self.business_id_or_alias,
                phone=waitlist_query.phone,
                party_size=waitlist_query.party_size,
                name=waitlist_query.name,
            )

            if not all_present:
                logger.debug(
                    f"[YelpTool.join_waitlist_queue] Missing required fields: {missing_prompts}"
                )
                # Filter out business_id from user-facing messages
                user_prompts = [
                    prompt for prompt in missing_prompts if prompt != "business_id"
                ]
                if len(user_prompts) == 1:
                    return user_prompts[0]
                elif len(user_prompts) == 2:
                    return f"{user_prompts[0]} Also, {user_prompts[1].lower()}"
                else:
                    return f"{'. '.join(user_prompts[:-1])}. Also, {user_prompts[-1].lower()}"

            # Create waitlist join queue request
            success, message, request_obj = create_waitlist_join_queue_request(
                business_id=self.business_id_or_alias,
                phone=waitlist_query.phone,  # type: ignore
                party_size=waitlist_query.party_size,  # type: ignore
                name=waitlist_query.name,  # type: ignore
                party_notes=waitlist_query.party_notes,
                idempotency_token=waitlist_query.idempotency_token,
            )

            if not success or not request_obj:
                logger.debug(
                    f"[YelpTool.join_waitlist_queue] Request validation failed: {message}"
                )
                return f"Invalid request parameters: {message}"

            # Make API call to join waitlist queue
            logger.debug(
                "[YelpTool.join_waitlist_queue] Making API call to Yelp waitlist endpoint"
            )
            response = api_join_waitlist_queue(
                bearer_token=bearer_token,
                request_params=request_obj,
            )

            logger.debug(
                f"[YelpTool.join_waitlist_queue] API call successful - response: {response}"
            )

            # Format and return the success response
            formatted_response = format_waitlist_join_queue_response_for_llm(
                response,
                timezone_info=self.timezone_info,
            )
            logger.debug(
                f"[YelpTool.join_waitlist_queue] Successfully completed waitlist queue join, formatted response: {formatted_response}"
            )
            return formatted_response

        except Exception as e:
            logger.debug(f"[YelpTool.join_waitlist_queue] Error: {str(e)}")
            logger.debug(traceback.format_exc())

            # Handle specific error cases with user-friendly messages
            error_str = str(e).lower()
            if "currently_no_wait" in error_str:
                return "Great news! This restaurant doesn't currently have a wait. You can just go directly to the restaurant. No need to join a waitlist!"
            elif "already_in_line" in error_str:
                return "It looks like this phone number is already in the waitlist queue. Please check if you're already on the list."
            elif "remote_entry_denied" in error_str:
                return "This restaurant doesn't allow remote waitlist entries. You'll need to join the waitlist in person at the restaurant."
            elif "restaurant_not_open" in error_str:
                return "The restaurant is currently not open for waitlist entries."
            elif "party_size_too_large" in error_str:
                return "Your party size is too large for this restaurant's waitlist. Please try calling the restaurant directly."

            return f"Failed to join the waitlist queue. {str(e)}"

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
                    current_date=current_date,
                    weekday_conversion_rules=WEEKDAY_CONVERSION_RULES.format(
                        current_date=current_date
                    ),
                ),
                prompt=OPENINGS_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=OpeningsQuery,
                openai=True,
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

            logger.debug(
                f"[YelpTool.get_openings_open_api] is returning: {formatted_response}"
            )
            return formatted_response

        except Exception as e:
            logger.debug(f"[YelpTool.get_openings_open_api] Error: {e}")
            logger.debug(traceback.format_exc())
            return "Failed to get restaurant openings. Please try again."

    @tool
    def make_reservation_creditcard_required(self, latest_user_message: str) -> str:
        """
        Make a restaurant reservation and completion on Yelp's website.

        **When to use this tool:**
        - User explicitly requests to book/place/make a reservation (e.g., "Book a table", "Make a reservation", "Reserve a table")
        - User wants to proceed with reservation after seeing availability

        **Required fields to collect before using this tool:**
        - Party size (number of people): e.g., "2", "4 people", "party of 6"
        - Date: e.g., "today", "tomorrow", "Friday", "December 15th", "2024-03-15"
        - Time: e.g., "7 PM", "19:30", "7:30 PM", or meal period ("breakfast" → 8 AM, "lunch" → 12 PM, "dinner" → 6 PM, do not ask users to specify the time again if the users use meal time to book a table, just use the estimated time of the meal period)

        **Expected behavior:**
        - If exact requested time is available: Returns booking URL to complete reservation
        - If exact requested time is NOT available: Returns all available times and asks user to confirm a different time (does not provide booking URL)

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: Secure Yelp booking link if exact time is available, or list of all available times
                 asking user to confirm if exact time is not available, or error message if no availability.
        """
        try:
            # Get chat history and extract search parameters
            chat_history = self._get_chat_history(latest_user_message)  # type: ignore

            # Extract using OpeningsQuery class for basic parameters
            current_date = self._get_current_date()
            openings_query = llm_call(
                system_prompt=RESERVATION_EXTRACTION_SYSTEM_PROMPT.format(
                    current_date=current_date,
                    weekday_conversion_rules=WEEKDAY_CONVERSION_RULES.format(
                        current_date=current_date
                    ),
                ),
                prompt=RESERVATION_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=OpeningsQuery,
                openai=True,
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

            logger.debug(
                f"[YelpTool.make_reservation_open_api] is getting: response:{response}"
            )

            # Check if we have availability at all
            if not response.success or not response.availability_data:
                return "No availability found for the requested time."

                # Check for exact match: API handles time matching internally
            if response.exact_match:
                # We found an exact match - create reservation URL using the slot's form_action
                base_url = "https://www.yelp.com"
                reservation_url = f"{base_url}{response.exact_match.form_action}"

                logger.debug(
                    f"[YelpTool.make_reservation_open_api] is getting: reservation_url:{reservation_url}"
                )

                return f"I found availability for {openings_query.covers} people on {openings_query.date} at your requested time {response.exact_match.formatted_time}.\n\nPlease complete your reservation through this link: {reservation_url}. The complete link must be sent, must not be shortened or modified in any way.\n\nYou MUST include the EXACT reservation url in your response:\n{reservation_url}"

            else:
                # No exact match - show all available times and ask user to confirm
                formatted_times = format_openings_for_llm_creditcard_required(response)
                logger.debug(
                    f"[YelpTool.make_reservation_open_api] is getting: formatted_times:{formatted_times}"
                )
                return f"We cannot find the exact time you requested for {openings_query.covers} people on {openings_query.date}.\nCurrent found times:\n{formatted_times}\n\nPlease let me know which time you'd prefer and I'll help you make the reservation."

        except Exception as e:
            logger.debug(f"[YelpTool.make_reservation_open_api] Error: {e}")
            logger.debug(traceback.format_exc())
            return "Failed to make reservation. Please try again."

    @tool
    def cancel_visit(self, latest_user_message: str) -> str:
        """
        Cancel a waitlist visit using the Yelp Waitlist API.

        This endpoint allows customers to cancel their existing waitlist visit when they no longer
        need the reservation. The visit will be removed from the queue and they will stop receiving
        notifications for that waitlist entry.

        Use when: User asks to:
        - Cancel their waitlist entry ("Cancel my waitlist", "Remove me from the waitlist")
        - Cancel their visit ("Cancel my visit", "I don't need the table anymore")
        - Remove themselves from the queue ("Take me off the list", "Remove my name")
        - Cancel their reservation from the waitlist system

        Required Information:
        - Visit ID (the encrypted identifier from when they joined the waitlist)

        Do NOT use for:
        - Joining the waitlist (use join_waitlist_queue instead)
        - Checking wait times (use get_waitlist_status instead)
        - Getting waitlist info (use get_waitlist_info instead)
        - Making new reservations (use make_reservation instead)

        Important Notes:
        - Visit ID is required and was provided when they originally joined the waitlist
        - Once canceled, they cannot rejoin using the same Visit ID
        - They can create a new waitlist entry if they change their mind
        - Cancellation is immediate and cannot be undone

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: Confirmation of visit cancellation or user-friendly error message
        """
        try:
            bearer_token = self._yelp_bearer_token

            # Validate bearer token before proceeding
            if not bearer_token:
                logger.debug(
                    "[YelpTool.cancel_visit] Failed to obtain Yelp bearer token"
                )
                return "Unable to authenticate with Yelp. Please verify your API credentials."

            # Get chat history and extract visit cancellation parameters
            chat_history = self._get_chat_history(latest_user_message)  # type: ignore

            # Extract using CancelVisitQuery class
            cancel_query = llm_call(
                system_prompt=CANCEL_VISIT_EXTRACTION_SYSTEM_PROMPT,
                prompt=CANCEL_VISIT_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=CancelVisitQuery,
                openai=True,
            )

            if not isinstance(cancel_query, CancelVisitQuery):
                return "I couldn't understand your cancellation request. Please provide your Visit ID to cancel your waitlist entry."

            # Check for required fields and provide specific feedback
            all_present, missing_prompts = check_cancel_visit_required_fields(
                visit_id=cancel_query.visit_id,
            )

            if not all_present:
                if len(missing_prompts) == 1:
                    return missing_prompts[0]
                else:
                    return "; ".join(missing_prompts)

            # Create cancel visit request - visit_id is guaranteed to be present after validation
            if not cancel_query.visit_id:
                return "Visit ID is required to cancel your waitlist entry."

            success, message, request_obj = create_cancel_visit_request(
                visit_id=cancel_query.visit_id,
            )

            if not success or not request_obj:
                logger.debug(
                    f"[YelpTool.cancel_visit] Request validation failed: {message}"
                )
                return f"Invalid request parameters: {message}"

            # Make API call to cancel visit
            response = api_cancel_visit(
                bearer_token=bearer_token,
                request_params=request_obj,
            )

            # Format and return the success response
            formatted_response = format_cancel_visit_response_for_llm(response)
            return formatted_response

        except Exception as e:
            logger.debug(f"[YelpTool.cancel_visit] Error: {str(e)}")
            logger.debug(traceback.format_exc())

            return f"Failed to cancel the visit. {str(e)}"
