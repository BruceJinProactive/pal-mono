import re
import threading
import traceback
from typing import Optional

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.base.reservation import BaseReservationTool, params_validate
from tools.yelp_credit_card_tool._apis import (
    get_openings_creditcard_required,
    get_waitlist_status,
)
from tools.yelp_credit_card_tool._apis import (
    join_waitlist_queue as api_join_waitlist_queue,
)
from tools.yelp_credit_card_tool.classes import (
    YelpAccessToken,
    YelpBookingsOpeningsRequestCreditCardRequired,
)
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

_CACHED_BEARER_TOKEN: Optional[YelpAccessToken] = None
_CACHED_BEARER_TOKEN_LOCK = threading.Lock()


class YelpCreditCardTool(Toolkit, BaseReservationTool):
    # Required fields for each tool method (BaseReservationTool interface)
    REQUIRED_CHECK_AVAILABILITY_FIELDS = ["party_size", "date", "time"]
    REQUIRED_MAKE_RESERVATION_FIELDS = ["party_size", "date", "time"]
    REQUIRED_JOIN_WAITLIST_QUEUE_FIELDS = ["name", "party_size"]

    def __init__(
        self,
        business_id_or_alias: str,
        tool_metadata: ToolMetadata,
        biz_id: Optional[str] = None,
        biz_lat: Optional[str] = None,
        biz_long: Optional[str] = None,
    ):
        """
        Initialize YelpCreditCardTool for restaurants requiring credit card for reservations.

        This tool uses the credit card workflow exclusively, where reservations require
        users to complete the booking through Yelp's website with credit card information.

        Args:
            business_id_or_alias: The Yelp business ID or alias
            tool_metadata: Tool metadata containing session information
            biz_id: Business-specific ID parameter (required)
            biz_lat: Business latitude parameter (required)
            biz_long: Business longitude parameter (required)

        Raises:
            ValueError: If any of biz_id, biz_lat, or biz_long are not provided
        """
        super().__init__(name="yelp_credit_card_tool")

        self.business_id_or_alias = business_id_or_alias
        self.tool_metadata = tool_metadata

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

        # Register credit card workflow tools (BaseReservationTool interface)
        self.register(self.check_availability)
        self.register(self.make_reservation)

        # Register waitlist tools (independent of credit card workflow)
        self.register(self.get_waitlist_status)
        self.register(self.join_waitlist_queue)

        logger.debug(
            f"[YelpCreditCardTool]: __init__ - YelpCreditCardTool instance created: business id={self.business_id_or_alias}"
        )

    def _reset_and_refetch_token(self) -> YelpAccessToken:
        """Reset the cached bearer token and fetch a fresh one."""
        global _CACHED_BEARER_TOKEN
        with _CACHED_BEARER_TOKEN_LOCK:
            _CACHED_BEARER_TOKEN = None
            # Fetch fresh API key
            api_key = get_client_secret_with_fallback("YELP_API_KEY")
            if not api_key:
                raise Exception("Failed to obtain Yelp API key")
            # Create and cache the new bearer token
            _CACHED_BEARER_TOKEN = YelpAccessToken(
                access_token=api_key, token_type="Bearer"
            )
            return _CACHED_BEARER_TOKEN

    def _is_401_error(self, error: Exception) -> bool:
        """Check if the error is a 401 Unauthorized error."""
        error_str = str(error).lower()
        return "status 401" in error_str

    def _yelp_bearer_token(self) -> YelpAccessToken:
        """Get Yelp bearer token with caching to avoid repeated secret fetching."""
        global _CACHED_BEARER_TOKEN

        # Use double-checked locking pattern for thread safety
        with _CACHED_BEARER_TOKEN_LOCK:
            # Check if token was created by another thread while waiting for lock
            if _CACHED_BEARER_TOKEN is not None:
                return _CACHED_BEARER_TOKEN

            # Fetch the API key from secrets
            api_key = get_client_secret_with_fallback("YELP_API_KEY")

            if not api_key:
                raise Exception("Failed to obtain Yelp API key")

            # Create and cache the bearer token
            _CACHED_BEARER_TOKEN = YelpAccessToken(
                access_token=api_key, token_type="Bearer"
            )
            return _CACHED_BEARER_TOKEN

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
        - Joining the waitlist (use join_waitlist_queue)
        - General restaurant information

        Returns:
            str: Raw API response containing waitlist status data, or error message
        """
        try:
            bearer_token = self._yelp_bearer_token()

            # Validate bearer token before proceeding
            if not bearer_token:
                logger.debug(
                    "[YelpCreditCardTool]: get_waitlist_status - Failed to obtain Yelp bearer token"
                )
                return "Unable to authenticate with Yelp. Please verify your API credentials."

            # Get waitlist status from Yelp API
            response = get_waitlist_status(
                bearer_token=bearer_token,
                business_id=self.business_id_or_alias,
            )

            return str(response)

        except Exception as e:
            logger.debug(
                f"[YelpCreditCardTool]: get_waitlist_status - Error: {str(e)}, {traceback.format_exc()}"
            )
            if self._is_401_error(e):
                logger.debug(
                    "[YelpCreditCardTool]: get_waitlist_status - 401 error detected, resetting cached token and retrying"
                )
                try:
                    response = get_waitlist_status(
                        bearer_token=self._reset_and_refetch_token(),
                        business_id=self.business_id_or_alias,
                    )
                    return str(response)
                except Exception as retry_e:
                    logger.debug(
                        f"[YelpCreditCardTool]: get_waitlist_status - Retry failed: {str(retry_e)}"
                    )
                    return f"Failed to get waitlist status after retry. {str(retry_e)}"
            return f"Failed to get waitlist status. {str(e)}"

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

        Note: Uses customer phone number from tool metadata. Phone must be in valid format.

        Args:
            name: Full name of the person for the waitlist (must not be empty)
            party_size: Number of people in the party (must be greater than 0)
            notes: Additional notes or special requests for the waitlist visit (optional)

        Returns:
            str: Raw API response containing waitlist queue confirmation data, or error message
        """
        # Use customer phone from metadata
        customer_phone = self.tool_metadata.customer_phone
        if not customer_phone:
            return "What phone number should I use for the waitlist?"

        # Normalize phone number to E.164 format
        try:
            # Remove all non-digit characters except +
            cleaned = re.sub(r"[^\d+]", "", customer_phone)
            digits_only = re.sub(r"[^\d]", "", cleaned)

            # If already in E.164 format, use as-is
            if cleaned.startswith("+"):
                normalized_phone = cleaned
            elif len(digits_only) == 10:
                normalized_phone = f"+1{digits_only}"
            elif len(digits_only) == 11 and digits_only.startswith("1"):
                normalized_phone = f"+{digits_only}"
            else:
                normalized_phone = f"+{digits_only}"
        except Exception:
            return "Please provide a valid phone number for the waitlist."

        try:
            logger.debug(
                "[YelpCreditCardTool]: join_waitlist_queue - Starting waitlist queue join request"
            )
            bearer_token = self._yelp_bearer_token()

            # Validate bearer token before proceeding
            if not bearer_token:
                logger.debug(
                    "[YelpCreditCardTool]: join_waitlist_queue - Failed to obtain Yelp bearer token"
                )
                return "Unable to authenticate with Yelp. Please verify your API credentials."

            # Make API call to join waitlist queue
            logger.debug(
                "[YelpCreditCardTool]: join_waitlist_queue - Making API call to Yelp waitlist endpoint"
            )
            response = api_join_waitlist_queue(
                bearer_token=bearer_token,
                business_id=self.business_id_or_alias,
                phone=normalized_phone,
                party_size=party_size,
                name=name.strip(),
                party_notes=notes.strip() if notes else None,
            )

            logger.debug(
                f"[YelpCreditCardTool]: join_waitlist_queue - API call successful - response: {response}"
            )

            return str(response)

        except Exception as e:
            logger.debug(
                f"[YelpCreditCardTool]: join_waitlist_queue - Error: {str(e)}, {traceback.format_exc()}"
            )
            if self._is_401_error(e):
                logger.debug(
                    "[YelpCreditCardTool]: join_waitlist_queue - 401 error detected, resetting cached token and retrying"
                )
                try:
                    # Reset cache and get fresh token, then retry
                    response = api_join_waitlist_queue(
                        bearer_token=self._reset_and_refetch_token(),
                        business_id=self.business_id_or_alias,
                        phone=normalized_phone,
                        party_size=party_size,
                        name=name.strip(),
                        party_notes=notes.strip() if notes else None,
                    )
                    return str(response)
                except Exception as retry_e:
                    logger.debug(
                        f"[YelpCreditCardTool]: join_waitlist_queue - Retry failed: {str(retry_e)}"
                    )
                    return (
                        f"Failed to join the waitlist queue after retry. {str(retry_e)}"
                    )
            return f"Failed to join the waitlist queue. {str(e)}"

    @tool
    @params_validate()
    def check_availability(self, party_size: int, date: str, time: str) -> str:  # type: ignore[misc]
        """
        Check availability for restaurant reservations (Credit Card Required).

        Use when: User wants to check availability or see time options before booking.
        This restaurant requires credit card information to complete reservations.

        Args:
            party_size: Number of people for the reservation (min: 1, max: 10)
            date: Desired reservation date in YYYY-MM-DD format (e.g., "2024-12-25")
            time: Desired reservation time in HH:MM format (24-hour, e.g., "18:30")

        Returns:
            str: Raw API response containing availability data, or error message
        """
        # Convert time format from HH:MM to HH:MM:SS for the API
        time_formatted = f"{time}:00"

        # Create request object directly from provided parameters
        request_obj = YelpBookingsOpeningsRequestCreditCardRequired(
            covers=party_size,
            date=date,
            time=time_formatted,
            biz_id=self.biz_id,  # type: ignore
            biz_lat=self.biz_lat,  # type: ignore
            biz_long=self.biz_long,  # type: ignore
            num_results_after=20,
            num_results_before=20,
        )

        try:
            # Make API call directly
            response = get_openings_creditcard_required(
                business_id_or_alias=self.business_id_or_alias,
                request_params=request_obj,
            )

            return str(response)

        except Exception as e:
            logger.debug(
                f"[YelpCreditCardTool]: check_availability - Error: {str(e)}, {traceback.format_exc()}"
            )
            if self._is_401_error(e):
                logger.debug(
                    "[YelpCreditCardTool]: check_availability - 401 error detected, resetting cached token and retrying"
                )
                try:
                    # Reset cache and get fresh token, then retry
                    response = get_openings_creditcard_required(
                        business_id_or_alias=self.business_id_or_alias,
                        request_params=request_obj,
                    )
                    return str(response)
                except Exception as retry_e:
                    logger.debug(
                        f"[YelpCreditCardTool]: check_availability - Retry failed: {str(retry_e)}"
                    )
                    return (
                        f"Failed to get restaurant openings after retry. {str(retry_e)}"
                    )
            return f"Failed to get restaurant openings. {str(e)}"

    @tool
    @params_validate()
    def make_reservation(  # type: ignore[misc]
        self,
        party_size: int,
        date: str,
        time: str,
    ) -> str:
        """
        Make a restaurant reservation (Credit Card Required).

        **When to use this tool:**
        - User explicitly requests to book/place/make a reservation (e.g., "Book a table", "Make a reservation", "Reserve a table")
        - User wants to proceed with reservation after seeing availability

        **Expected behavior:**
        - If exact requested time is available: Returns booking URL to complete reservation
        - If exact requested time is NOT available: Returns all available times and asks user to confirm a different time (does not provide booking URL)

        Note: This workflow requires completing the reservation on Yelp's website with credit card information.

        Args:
            party_size: Number of people for the reservation (min: 1, max: 10)
            date: Desired reservation date in YYYY-MM-DD format (e.g., "2024-12-25")
            time: Desired reservation time in HH:MM format (24-hour, e.g., "18:30")

        Returns:
            str: Raw API response containing availability data and booking URLs, or error message if no availability.
        """
        # Convert time format from HH:MM to HH:MM:SS for the API
        time_formatted = f"{time}:00"

        # Create request object directly from provided parameters
        request_obj = YelpBookingsOpeningsRequestCreditCardRequired(
            covers=party_size,
            date=date,
            time=time_formatted,
            biz_id=self.biz_id,  # type: ignore
            biz_lat=self.biz_lat,  # type: ignore
            biz_long=self.biz_long,  # type: ignore
            num_results_after=20,
            num_results_before=20,
        )

        try:
            # Get availability data
            response = get_openings_creditcard_required(
                business_id_or_alias=self.business_id_or_alias,
                request_params=request_obj,
            )

            logger.debug(
                f"[YelpCreditCardTool]: make_reservation - response: {response}"
            )

            return str(response)

        except Exception as e:
            logger.debug(
                f"[YelpCreditCardTool]: make_reservation - Error: {str(e)}, {traceback.format_exc()}"
            )
            if self._is_401_error(e):
                logger.debug(
                    "[YelpCreditCardTool]: make_reservation - 401 error detected, resetting cached token and retrying"
                )
                try:
                    # Reset cache and get fresh token, then retry
                    response = get_openings_creditcard_required(
                        business_id_or_alias=self.business_id_or_alias,
                        request_params=request_obj,
                    )
                    return str(response)
                except Exception as retry_e:
                    logger.debug(
                        f"[YelpCreditCardTool]: make_reservation - Retry failed: {str(retry_e)}"
                    )
                    return f"Failed to make reservation after retry. {str(retry_e)}"
            return f"Failed to make reservation. {str(e)}"

    def get_user_wait_status(self) -> str:  # type: ignore[misc]
        """
        Get today's waitlist entries for a specific phone number.

        Note: This functionality is not currently supported by Yelp's waitlist API.

        Returns:
            str: Message indicating that user wait status is not supported
        """
        return "User wait status lookup is not supported by Yelp waitlist API."
