import traceback
from datetime import datetime
from functools import cached_property
from typing import Optional
from zoneinfo import ZoneInfo

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.base.reservation import BaseReservationTool, params_validate
from tools.utils.ordering._llm import llm_call
from tools.yelp_no_credit_card_tool._apis import cancel_visit as api_cancel_visit
from tools.yelp_no_credit_card_tool._apis import (
    create_hold_creditcard_not_required,
    create_waitlist_on_my_way,
    get_openings_creditcard_not_required,
    get_waitlist_info,
    get_waitlist_status,
)
from tools.yelp_no_credit_card_tool._apis import (
    join_waitlist_queue as api_join_waitlist_queue,
)
from tools.yelp_no_credit_card_tool._prompt_constants import (
    CANCEL_VISIT_EXTRACTION_SYSTEM_PROMPT,
    CANCEL_VISIT_EXTRACTION_USER_PROMPT,
    WAITLIST_ON_MY_WAY_EXTRACTION_SYSTEM_PROMPT,
    WAITLIST_ON_MY_WAY_EXTRACTION_USER_PROMPT,
)
from tools.yelp_no_credit_card_tool._utils import (
    OPENINGS_ANY_TIME_LIST_COUNT,
    OPENINGS_DEFAULT_LIST_COUNT,
    check_cancel_visit_required_fields,
    check_waitlist_join_queue_required_fields,
    check_waitlist_on_my_way_required_fields,
    create_cancel_visit_request,
    create_holds_request_creditcard_not_required,
    create_openings_request_creditcard_not_required,
    create_reservation_from_hold_creditcard_not_required,
    create_waitlist_info_request,
    create_waitlist_join_queue_request,
    create_waitlist_on_my_way_request,
    create_waitlist_status_request,
    format_cancel_visit_response_for_llm,
    format_openings_for_llm_creditcard_not_required,
    format_waitlist_info_for_llm,
    format_waitlist_join_queue_response_for_llm,
    format_waitlist_on_my_way_response_for_llm,
    format_waitlist_status_for_llm,
)
from tools.yelp_no_credit_card_tool.classes import (
    CancelVisitQuery,
    OpeningsQuery,
    WaitlistOnMyWayQuery,
    YelpAccessToken,
)
from utils.log import logger
from utils.secret import get_client_secret_with_fallback


class YelpNoCreditCardTool(Toolkit, BaseReservationTool):
    # Required fields for each tool method (BaseReservationTool interface)
    REQUIRED_CHECK_AVAILABILITY_FIELDS = ["party_size", "date", "time"]
    REQUIRED_MAKE_RESERVATION_FIELDS = ["party_size", "date", "time"]
    REQUIRED_JOIN_WAITLIST_QUEUE_FIELDS = ["name", "party_size"]

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
        Initialize YelpNoCreditCardTool for restaurants that don't require credit cards for reservations.

        This tool uses the official Yelp integration API exclusively, providing instant reservation
        confirmation without requiring credit card information from users.

        Args:
            business_id_or_alias: The Yelp business ID or alias
            tool_metadata: Tool metadata containing session information
            credit_card_required: Whether this business actually requires credit card for reservations (ignored, always treated as False)
            yelp_integration_api: Use Yelp official integration API workflow (ignored, always uses non-credit card workflow)
            biz_id: Business-specific ID parameter (ignored for non-credit card workflow)
            biz_lat: Business latitude parameter (ignored for non-credit card workflow)
            biz_long: Business longitude parameter (ignored for non-credit card workflow)
            waitlist_enabled: Whether to enable waitlist functionality (default: False)
            reservation_enabled: Whether to enable reservation functionality (default: True)
        """
        super().__init__(name="yelp_no_credit_card_tool")

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

        # Force non-credit card workflow for this tool
        self.use_creditcard_workflow = False

        # Register reservation tools
        if reservation_enabled:
            # Non-credit card workflow doesn't need business parameters
            self.biz_id = None
            self.biz_lat = None
            self.biz_long = None

            # Register non-credit card workflow tools (BaseReservationTool interface)
            self.register(self.check_availability)
            self.register(self.make_reservation)
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
            f"YelpNoCreditCardTool instance created: business id={self.business_id_or_alias}, credit_card_required={credit_card_required}, yelp_integration_api={yelp_integration_api}, use_creditcard_workflow={self.use_creditcard_workflow}, waitlist_enabled={waitlist_enabled}, reservation_enabled={reservation_enabled}"
        )

    def _get_result_limits_for_query(
        self, openings_query: OpeningsQuery
    ) -> tuple[Optional[int], Optional[int]]:
        """
        Helper method to determine result limits for openings queries.
        Handles "any time" requests by setting full list retrieval.

        Args:
            openings_query: The parsed openings query from LLM extraction

        Returns:
            Tuple of (num_results_before, num_results_after)
        """
        # Check if this is an "any time" request (both after and before are true)
        if openings_query.after and openings_query.before:
            # Set to retrieve full list of openings (results before and after the default 12:30 PM time)
            num_results_after = OPENINGS_ANY_TIME_LIST_COUNT
            num_results_before = OPENINGS_ANY_TIME_LIST_COUNT
            logger.info(
                f"[YelpTool] Detected 'any time' request, setting full list retrieval: before={num_results_before}, after={num_results_after}"
            )
        else:
            # Handle normal filtering logic
            num_results_after = 0 if openings_query.before else None
            num_results_before = 0 if openings_query.after else None

            # If one value is 0 (filtering) and the other is None, set the None to default count
            if num_results_after == 0 and num_results_before is None:
                num_results_before = OPENINGS_DEFAULT_LIST_COUNT
            elif num_results_before == 0 and num_results_after is None:
                num_results_after = OPENINGS_DEFAULT_LIST_COUNT
            # If both are None (no filtering specified), set both to default count
            elif num_results_before is None and num_results_after is None:
                num_results_before = OPENINGS_DEFAULT_LIST_COUNT
                num_results_after = OPENINGS_DEFAULT_LIST_COUNT

        return num_results_before, num_results_after

    def _process_name_for_reservation(
        self, first_name: Optional[str], last_name: Optional[str]
    ) -> tuple[str, str]:
        """
        Process name inputs for Yelp reservations with phone identification.

        Args:
            first_name: Optional first name from user input
            last_name: Optional last name from user input

        Returns:
            tuple[str, str]: (processed_first_name, processed_last_name_with_phone)
        """
        # Get customer phone from tool metadata
        customer_phone = self.tool_metadata.customer_phone

        # Extract last 4 digits
        if customer_phone and len(customer_phone) >= 4:
            last_four = customer_phone[-4:]
        else:
            last_four = "0000"
            if not customer_phone:
                logger.warning(
                    "[YelpTool._process_name_for_reservation] No customer phone available in tool metadata"
                )
            else:
                logger.warning(
                    f"[YelpTool._process_name_for_reservation] Customer phone '{customer_phone}' is too short (< 4 digits), using '0000' as fallback"
                )

        # Process first name (use as-is)
        processed_first_name = first_name.strip() if first_name else ""

        # Process last name with phone digits
        if last_name and last_name.strip():
            processed_last_name = f"{last_name.strip()} (*{last_four} via Palona)"
        else:
            processed_last_name = f"(*{last_four} via Palona)"

        return processed_first_name, processed_last_name

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
    def _get_chat_history(self) -> str:
        """
        Retrieves the chat history from the query messages tool.

        Returns:
            str: A string representing the entire chat history.
        """
        chat_history: str = self.query_messages_tool.query_messages()  # type: ignore
        if not chat_history:
            logger.warning("[YelpTool._get_chat_history] Empty chat history returned")

        LLMObs.annotate(output_data=chat_history)
        return chat_history

    @tool
    @params_validate()
    def check_availability(self, party_size: int, date: str, time: str) -> str:  # type: ignore[misc]
        """
        Check availability for restaurant reservations (No Credit Card Required).

        Use when: User wants to check availability or see time options before booking.
        This restaurant provides instant confirmation without requiring credit card information.

        Args:
            party_size: Number of people for the reservation (1-10)
            date: Desired reservation date in YYYY-MM-DD format
            time: Desired reservation time in HH:MM format (24-hour)

        Returns:
            str: Formatted string containing available reservation times, or error message
        """
        try:
            bearer_token = self._yelp_bearer_token

            # Create request object directly from provided parameters
            success, message, request_obj = (
                create_openings_request_creditcard_not_required(
                    business_id_or_alias=self.business_id_or_alias,
                    covers=party_size,
                    date=date,
                    time=time,
                    get_covers_range=False,  # Default to False
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
        Make a restaurant reservation (No Credit Card Required).

        **When to use this tool:**
        - User explicitly requests to book/place/make a reservation (e.g., "Book a table", "Make a reservation", "Reserve a table for tonight")
        - User has provided or confirms all required reservation details

        This restaurant provides instant confirmation without requiring credit card validation.

        Args:
            name: Full name of the person making the reservation
            party_size: Number of people for the reservation (1-10)
            date: Desired reservation date in YYYY-MM-DD format
            time: Desired reservation time in HH:MM format (24-hour)
            email: Customer email address (optional, ignored)
            notes: Additional party notes and special requests for the reservation (optional)

        Returns:
            str: Reservation confirmation details with confirmation number, or error message if reservation fails.
        """
        try:
            bearer_token = self._yelp_bearer_token
            if not bearer_token:
                return "Unable to authenticate with Yelp. Please try again later."

            # Handle name processing - split full names or use Palona AI as fallback
            processed_first_name, processed_last_name = (
                self._process_name_for_reservation(
                    name.split()[0] if name else "",
                    " ".join(name.split()[1:]) if len(name.split()) > 1 else "",
                )
            )

            customer_phone = self.tool_metadata.customer_phone
            if not customer_phone:
                return "I need your phone number to complete the reservation."

            # Create hold
            import uuid

            hold_success, hold_message, hold_request = (
                create_holds_request_creditcard_not_required(
                    business_id_or_alias=self.business_id_or_alias,
                    covers=party_size,
                    date=date,
                    time=time,
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
                    error_prefix = f"This restaurant doesn't accept reservations for {party_size} people."
                elif "invalid_date_time_range" in error_msg:
                    error_prefix = f"The date/time {date} at {time} is invalid."
                else:
                    return f"Unable to place a hold for {time} on {date} due to {error_msg}"

                # Return simple error message
                return error_prefix

            # If credit card required, return URL
            if hold_response.credit_card_hold:
                if not hold_response.reserve_url:
                    return "This restaurant requires a credit card, but the booking link is not available."

                return f"I've placed a hold for {party_size} people on {date} at {time}.\n\nThis restaurant requires a credit card to complete the reservation.\n\nPlease complete your reservation here: {hold_response.reserve_url}\n\nNote: This hold expires in 5 minutes.\n\nYou MUST include the EXACT reservation url in your response:\n{hold_response.reserve_url}"

            # Handle notes with special requests - use default if none provided
            reservation_notes = notes if notes else "No special request"

            # Create reservation directly
            reservation_success, reservation_message, reservation_response = (
                create_reservation_from_hold_creditcard_not_required(
                    bearer_token=bearer_token,
                    holds_response=hold_response,
                    holds_request=hold_request,
                    first_name=processed_first_name,  # Use processed names
                    last_name=processed_last_name,  # Use processed names
                    phone=customer_phone,  # type: ignore
                    email="inbox@proactiveailab.com",  # Hardcoded email instead of asking user
                    notes=reservation_notes,
                )
            )

            if not reservation_success or not reservation_response:
                return f"Failed to create reservation: {reservation_message}"

            return f"Reservation confirmed! Here is the reservation details: {reservation_response}"

        except Exception as e:
            logger.debug(f"[YelpTool.make_reservation] Error: {e}")
            logger.debug(traceback.format_exc())
            return "Failed to make reservation. Please try again."

    def get_waitlist_status(self) -> str:  # type: ignore[misc]
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

        Args:
            None.

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

        Args:
            None.

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
    def create_waitlist_on_my_way_visit(
        self,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        party_size: Optional[int] = None,
        arrival_range_min: Optional[int] = None,
        arrival_range_max: Optional[int] = None,
        party_notes: Optional[str] = None,
    ) -> str:
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
            name: Full name of the person for the waitlist.
            phone: Phone number in E.164 format (e.g., +15551234567).
            party_size: Number of people in the party.
            arrival_range_min: Minimum expected arrival time in minutes from now (1-30).
            arrival_range_max: Maximum expected arrival time in minutes from now (1-30).
            party_notes: Additional notes or special requests for the waitlist visit.

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
            chat_history = self._get_chat_history()  # type: ignore

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
    @params_validate()
    def join_waitlist_queue(  # type: ignore[misc]
        self,
        name: str,
        party_size: int,
        notes: str = "",
    ) -> str:
        """
        Join the waitlist queue for a restaurant using the Yelp Waitlist API.

        Use when: User asks to:
        - Join the waitlist queue ("Put me on the waitlist", "Add me to the waitlist")
        - Get in line at a restaurant ("Can I get in line?", "I want to join the queue")
        - Add their party to the wait ("Put us on the list for a table")
        - Join the wait when they know there's currently a wait time

        Args:
            name: Full name of the person for the waitlist
            party_size: Number of people in the party
            notes: Additional notes or special requests for the waitlist visit (optional)

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

            # Use customer phone from metadata
            customer_phone = self.tool_metadata.customer_phone

            # Check for required fields and provide specific feedback
            logger.debug("[YelpTool.join_waitlist_queue] Validating required fields")

            all_present, missing_prompts = check_waitlist_join_queue_required_fields(
                business_id=self.business_id_or_alias,
                phone=customer_phone,
                party_size=party_size,
                name=name,
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
                phone=customer_phone,  # type: ignore
                party_size=party_size,
                name=name,
                party_notes=notes if notes else None,
                idempotency_token=None,  # Generate if needed internally
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
    def cancel_visit(
        self,
        visit_id: Optional[str] = None,
    ) -> str:
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
            visit_id: The encrypted visit identifier from when they joined the waitlist.

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
            chat_history = self._get_chat_history()  # type: ignore

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

    def get_user_wait_status(self) -> str:  # type: ignore[misc]
        """
        Get today's waitlist entries for a specific phone number.

        Note: This functionality is not currently supported by Yelp's waitlist API.

        Returns:
            str: Message indicating that user wait status is not supported
        """
        return "User wait status lookup is not supported by Yelp waitlist API."
