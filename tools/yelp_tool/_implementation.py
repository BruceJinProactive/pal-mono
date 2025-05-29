import traceback
import uuid
from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.yelp_tool._apis import (
    create_hold,
    create_reservation,
    get_openings,
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
    create_holds_request,
    create_openings_request,
    create_reservation_from_hold_response,
    create_waitlist_status_request,
    format_openings_for_llm,
    format_reservation_response_for_llm,
    format_waitlist_status_for_llm,
)
from tools.yelp_tool.classes import (
    OpeningsQuery,
    ReservationQuery,
    YelpAccessToken,
    YelpAccessTokenRequest,
)
from utils.log import logger
from utils.ordering._llm import llm_call
from utils.secret import get_client_secret_with_fallback


class YelpTool(Toolkit):
    def __init__(
        self,
        business_id_or_alias: str,
        namespace: str,
        index_name: str,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="yelp_tool")

        self.business_id_or_alias = business_id_or_alias
        self.namespace = namespace
        self.index_name = index_name
        self.tool_metadata = tool_metadata

        self.register(self.get_restaurant_openings)
        self.register(self.make_reservation)
        self.register(self.get_waitlist_status)

        # Initialize query messages tool
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

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
    def get_restaurant_openings(self, latest_user_message: str) -> str:
        """
        Get available reservation times for a restaurant using the Yelp Bookings API.

        This function extracts reservation search parameters from the conversation history
        and returns available reservation times around the requested timeslot.

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
            openings_query = llm_call(
                system_prompt=OPENINGS_EXTRACTION_SYSTEM_PROMPT,
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

            success, message, request_obj = create_openings_request(
                business_id_or_alias=self.business_id_or_alias,
                covers=openings_query.covers,
                date=openings_query.date,
                time=openings_query.time,
                get_covers_range=openings_query.get_covers_range,
            )

            if not success or not request_obj:
                return f"Invalid request parameters: {message}"

            response = get_openings(
                bearer_token=bearer_token,
                request_params=request_obj,
            )

            formatted_response = format_openings_for_llm(response)
            return formatted_response

        except Exception as e:
            logger.debug(
                f"[YelpTool.get_restaurant_openings] Error getting openings: {e}"
            )
            logger.debug(traceback.format_exc())
            return "Failed to get restaurant openings. Please try again."

    @tool
    def make_reservation(self, latest_user_message: str) -> str:
        """
        Make a reservation for a restaurant using the Yelp Bookings API.

        This function extracts complete reservation details from the conversation history,
        creates a hold first, then immediately makes the reservation.
        The entire process is handled in a single tool call for user convenience.

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: Formatted string containing reservation confirmation details, or error message
        """
        try:
            bearer_token = self._yelp_bearer_token

            # Validate bearer token before proceeding
            if not bearer_token:
                logger.debug(
                    "[YelpTool.make_reservation] Failed to obtain Yelp bearer token"
                )
                return "Unable to authenticate with Yelp. Please try again later."

            unique_id = str(
                uuid.uuid4()
            )  # NOTE: Generate MOCK unique ID for testing purposes

            # Get chat history and extract reservation parameters
            chat_history = self._get_chat_history(latest_user_message)  # type: ignore

            # Extract using ReservationQuery class
            reservation_query = llm_call(
                system_prompt=RESERVATION_EXTRACTION_SYSTEM_PROMPT,
                prompt=RESERVATION_EXTRACTION_USER_PROMPT.format(
                    chat_history=chat_history
                ),
                response_format=ReservationQuery,
                reasoning=False,
            )

            if not isinstance(reservation_query, ReservationQuery):
                return "I couldn't understand your reservation request. Please provide all the necessary details for making a reservation."

            # Validate required fields
            required_fields = {
                "covers": reservation_query.covers,
                "date": reservation_query.date,
                "time": reservation_query.time,
                "first_name": reservation_query.first_name,
                "last_name": reservation_query.last_name,
                "phone": reservation_query.phone,
                "email": reservation_query.email,
            }

            missing_fields = [
                field_name for field_name, value in required_fields.items() if not value
            ]

            if missing_fields:
                field_map = {
                    "covers": "number of people",
                    "date": "reservation date",
                    "time": "reservation time",
                    "first_name": "first name",
                    "last_name": "last name",
                    "phone": "phone number",
                    "email": "email address",
                }

                missing_display = [
                    field_map.get(field, field) for field in missing_fields
                ]
                return f"To make a reservation, I need the following information: {', '.join(missing_display)}. Please provide these details."

            # At this point, all required fields are validated to be non-None
            assert reservation_query.covers is not None
            assert reservation_query.date is not None
            assert reservation_query.time is not None
            assert reservation_query.first_name is not None
            assert reservation_query.last_name is not None
            assert reservation_query.phone is not None
            assert reservation_query.email is not None

            # Step 1: Create a hold
            logger.debug(
                f"[YelpTool.make_reservation] Creating hold for {reservation_query.covers} people on {reservation_query.date} at {reservation_query.time}"
            )

            hold_success, hold_message, hold_request = create_holds_request(
                business_id_or_alias=self.business_id_or_alias,
                covers=reservation_query.covers,
                date=reservation_query.date,
                time=reservation_query.time,
                unique_id=unique_id,
            )

            if not hold_success or not hold_request:
                return f"Failed to create reservation hold: {hold_message}"

            # Step 2: Create a hold with proper error handling
            try:
                hold_response = create_hold(
                    bearer_token=bearer_token,
                    request_params=hold_request,
                )
            except Exception as exc:
                logger.debug(f"[YelpTool.make_reservation] create_hold failed: {exc}")
                logger.debug(traceback.format_exc())
                return "Yelp was unable to place a hold – please try again or choose another time."

            # Check if hold_response is valid before accessing attributes
            if not hold_response:
                logger.debug("[YelpTool.make_reservation] create_hold returned None")
                return "I couldn't create a hold with Yelp – please try again."

            # Verify hold_response has the expected hold_id attribute
            if not hasattr(hold_response, "hold_id") or not hold_response.hold_id:
                logger.debug(
                    "[YelpTool.make_reservation] hold_response missing or empty hold_id"
                )
                return "Yelp hold response was incomplete – please try again."

            logger.debug(
                f"[YelpTool.make_reservation] Hold created successfully with ID: {hold_response.hold_id}"
            )

            # Step 3: Create the reservation using the hold
            reservation_success, reservation_message, reservation_request = (
                create_reservation_from_hold_response(
                    holds_response=hold_response,
                    holds_request=hold_request,
                    first_name=reservation_query.first_name,
                    last_name=reservation_query.last_name,
                    phone=reservation_query.phone,
                    email=reservation_query.email,
                    notes=reservation_query.notes,
                )
            )

            if not reservation_success or not reservation_request:
                return f"Failed to create reservation request: {reservation_message}"

            # Step 4: Create the reservation with proper error handling
            try:
                reservation_response = create_reservation(
                    bearer_token=bearer_token,
                    request_params=reservation_request,
                )
            except Exception as exc:
                logger.debug(
                    f"[YelpTool.make_reservation] create_reservation failed: {exc}"
                )
                logger.debug(traceback.format_exc())
                return "Yelp rejected the reservation request – please verify details and try again."

            # Check if reservation_response is valid before accessing attributes
            if not reservation_response:
                logger.debug(
                    "[YelpTool.make_reservation] create_reservation returned None"
                )
                return "Yelp reservation response was empty – please try again."

            # Verify reservation_response has the expected reservation_id attribute
            if (
                not hasattr(reservation_response, "reservation_id")
                or not reservation_response.reservation_id
            ):
                logger.debug(
                    "[YelpTool.make_reservation] reservation_response missing or empty reservation_id"
                )
                return "Yelp reservation response was incomplete – please try again."

            logger.debug(
                f"[YelpTool.make_reservation] Reservation created successfully with ID: {reservation_response.reservation_id}"
            )

            # Format and return the reservation confirmation with error handling
            try:
                formatted_response = format_reservation_response_for_llm(
                    reservation_response
                )
                return formatted_response
            except Exception as exc:
                logger.debug(
                    f"[YelpTool.make_reservation] Failed to format reservation response: {exc}"
                )
                logger.debug(traceback.format_exc())
                # Return basic confirmation if formatting fails
                return f"Reservation confirmed! Your reservation ID is: {reservation_response.reservation_id}"

        except Exception as e:
            logger.debug(f"[YelpTool.make_reservation] Error making reservation: {e}")
            logger.debug(traceback.format_exc())
            return f"Failed to make reservation. Error: {str(e)}"

    @tool
    def get_waitlist_status(self) -> str:
        """
        Get waitlist status for a restaurant using the Yelp Waitlist API.

        This function retrieves waitlist status information including current wait times
        for different party sizes, the state of the waitlist, and any closure reason.

        Note: This endpoint requires the caller to be an onboarded Yelp Waitlist partner.

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
