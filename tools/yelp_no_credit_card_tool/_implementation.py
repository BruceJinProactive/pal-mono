import re
import threading
import traceback
from typing import Optional

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from tools.base.reservation import BaseReservationTool, params_validate
from tools.yelp_no_credit_card_tool._apis import (
    create_hold_creditcard_not_required,
    create_reservation_creditcard_not_required,
    get_openings_creditcard_not_required,
    get_waitlist_status,
)
from tools.yelp_no_credit_card_tool._apis import (
    join_waitlist_queue as api_join_waitlist_queue,
)
from tools.yelp_no_credit_card_tool.classes import YelpAccessToken
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

_CACHED_BEARER_TOKEN: Optional[YelpAccessToken] = None
_CACHED_BEARER_TOKEN_LOCK = threading.Lock()


class YelpNoCreditCardTool(Toolkit, BaseReservationTool):
    # Required fields for each tool method (BaseReservationTool interface)
    REQUIRED_CHECK_AVAILABILITY_FIELDS = ["party_size", "date", "time"]
    REQUIRED_MAKE_RESERVATION_FIELDS = ["name", "party_size", "date", "time"]
    REQUIRED_JOIN_WAITLIST_QUEUE_FIELDS = ["name", "party_size"]

    def __init__(
        self,
        business_id_or_alias: str,
        tool_metadata: ToolMetadata,
    ):
        """
        Initialize YelpNoCreditCardTool for restaurants that don't require credit cards for reservations.

        This tool uses the official Yelp integration API exclusively, providing instant reservation
        confirmation without requiring credit card information from users.

        Args:
            business_id_or_alias: The Yelp business ID or alias
            tool_metadata: Tool metadata containing session information
        """
        super().__init__(name="yelp_no_credit_card_tool")

        self.business_id_or_alias = business_id_or_alias
        self.tool_metadata = tool_metadata

        # Register non-credit card workflow tools (BaseReservationTool interface)
        self.register(self.check_availability)
        self.register(self.make_reservation)

        # Register waitlist tools (independent of credit card workflow)
        self.register(self.get_waitlist_status)
        self.register(self.join_waitlist_queue)

        logger.debug(
            f"[YelpNoCreditCardTool]: __init__ - YelpNoCreditCardTool instance created: business id={self.business_id_or_alias}"
        )

    def _reset_and_refetch_token(self) -> YelpAccessToken:
        """Reset the cached bearer token and fetch a fresh one."""
        global _CACHED_BEARER_TOKEN
        logger.debug(
            "[YelpNoCreditCardTool]: _reset_and_refetch_token - Resetting cached bearer token and fetching fresh token"
        )
        with _CACHED_BEARER_TOKEN_LOCK:
            _CACHED_BEARER_TOKEN = None
            # Fetch fresh API key
            api_key = get_client_secret_with_fallback("YELP_API_KEY")
            if not api_key:
                logger.debug(
                    "[YelpNoCreditCardTool]: _reset_and_refetch_token - Failed to obtain Yelp API key"
                )
                raise Exception("Failed to obtain Yelp API key")
            # Create and cache the new bearer token
            _CACHED_BEARER_TOKEN = YelpAccessToken(
                access_token=api_key, token_type="Bearer"
            )
            logger.debug(
                "[YelpNoCreditCardTool]: _reset_and_refetch_token - Successfully created and cached new bearer token"
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

    def _create_reservation_with_hold(
        self,
        bearer_token: YelpAccessToken,
        party_size: int,
        date: str,
        time: str,
        processed_first_name: str,
        processed_last_name: str,
        customer_phone: str,
        unique_id: str,
        reservation_notes: str,
    ) -> str:
        """Helper to create hold and reservation with given bearer token."""
        hold_response = create_hold_creditcard_not_required(
            bearer_token=bearer_token,
            business_id_or_alias=self.business_id_or_alias,
            covers=party_size,
            date=date,
            time=time,
            unique_id=unique_id,
        )

        if not hold_response or not hold_response.hold_id:
            return "Unable to place a hold. Please try again."

        if hold_response.credit_card_hold:
            if not hold_response.reserve_url:
                return "This restaurant requires a credit card, but the booking link is not available."

            return f"I've placed a hold for {party_size} people on {date} at {time}.\n\nThis restaurant requires a credit card to complete the reservation.\n\nPlease complete your reservation here: {hold_response.reserve_url}\n\nNote: This hold expires in 5 minutes.\n\nYou MUST include the EXACT reservation url in your response:\n{hold_response.reserve_url}"

        reservation_response = create_reservation_creditcard_not_required(
            bearer_token=bearer_token,
            business_id_or_alias=self.business_id_or_alias,
            covers=party_size,
            date=date,
            time=time,
            first_name=processed_first_name,
            last_name=processed_last_name,
            phone=customer_phone,  # type: ignore
            email="inbox@proactiveailab.com",
            hold_id=hold_response.hold_id,
            unique_id=unique_id,
            notes=reservation_notes,
        )

        return f"Reservation confirmed! Here is the reservation details: {reservation_response}"

    @tool
    @params_validate()
    def check_availability(self, party_size: int, date: str, time: str) -> str:  # type: ignore[misc]
        """
        Check availability for restaurant reservations (No Credit Card Required).

        Use when: User wants to check availability or see time options before booking.
        This restaurant provides instant confirmation without requiring credit card information.

        Args:
            party_size: Number of people for the reservation (min: 1, max: 10)
            date: Desired reservation date in YYYY-MM-DD format (e.g., "2024-12-25")
            time: Desired reservation time in HH:MM format (24-hour, e.g., "18:30")

        Returns:
            str: Raw API response containing available reservation times, or error message
        """
        try:
            bearer_token = self._yelp_bearer_token()

            # Make API call directly
            response = get_openings_creditcard_not_required(
                bearer_token=bearer_token,
                business_id_or_alias=self.business_id_or_alias,
                covers=party_size,
                date=date,
                time=time,
            )

            return str(response)

        except Exception as e:
            logger.debug(
                f"[YelpNoCreditCardTool]: check_availability - Error: {str(e)}, {traceback.format_exc()}"
            )
            if self._is_401_error(e):
                logger.debug(
                    "[YelpNoCreditCardTool]: check_availability - 401 error detected, resetting cached token and retrying"
                )
                try:
                    response = get_openings_creditcard_not_required(
                        bearer_token=self._reset_and_refetch_token(),
                        business_id_or_alias=self.business_id_or_alias,
                        covers=party_size,
                        date=date,
                        time=time,
                    )
                    return str(response)
                except Exception as retry_e:
                    logger.debug(
                        f"[YelpNoCreditCardTool]: check_availability - Retry failed: {str(retry_e)}"
                    )
                    return (
                        f"Failed to get restaurant openings after retry. {str(retry_e)}"
                    )
            return f"Failed to get restaurant openings. {str(e)}"

    @tool
    @params_validate()
    def make_reservation(  # type: ignore[misc]
        self,
        name: str,
        party_size: int,
        date: str,
        time: str,
        notes: str = "",
    ) -> str:
        """
        Make a restaurant reservation (No Credit Card Required).

        **When to use this tool:**
        - User explicitly requests to book/place/make a reservation (e.g., "Book a table", "Make a reservation", "Reserve a table")
        - User wants to proceed with reservation after seeing availability

        This restaurant provides instant confirmation without requiring credit card validation.

        Args:
            name: Full name of the person making the reservation
            party_size: Number of people for the reservation (min: 1, max: 10)
            date: Desired reservation date in YYYY-MM-DD format (e.g., "2024-12-25")
            time: Desired reservation time in HH:MM format (24-hour, e.g., "18:30")
            notes: Additional party notes and special requests for the reservation (optional)

        Returns:
            str: Reservation confirmation details with confirmation number, or error message if reservation fails.
        """
        # Handle name processing - split full names
        name_parts = name.split()
        processed_first_name = name_parts[0] if name_parts else ""
        processed_last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        # Get customer phone from metadata
        customer_phone = self.tool_metadata.customer_phone
        if not customer_phone:
            return "I need your phone number to complete the reservation."

        # Extract last 4 digits for name identification
        if customer_phone and len(customer_phone) >= 4:
            last_four = customer_phone[-4:]
        else:
            last_four = "0000"
            if not customer_phone:
                logger.warning(
                    "[YelpNoCreditCardTool]: make_reservation - No customer phone available in tool metadata"
                )
            else:
                logger.warning(
                    f"[YelpNoCreditCardTool]: make_reservation - Customer phone '{customer_phone}' is too short (< 4 digits), using '0000' as fallback"
                )

        # Process last name with phone digits
        if processed_last_name:
            processed_last_name = f"{processed_last_name} (*{last_four} via Palona)"
        else:
            processed_last_name = f"(*{last_four} via Palona)"

        # Create hold
        import uuid

        unique_id = str(uuid.uuid4())

        # Handle notes with special requests - use default if none provided
        reservation_notes = notes if notes else "No special request"

        try:
            bearer_token = self._yelp_bearer_token()
            if not bearer_token:
                return "Unable to authenticate with Yelp. Please try again later."

            try:
                return self._create_reservation_with_hold(
                    bearer_token=bearer_token,
                    party_size=party_size,
                    date=date,
                    time=time,
                    processed_first_name=processed_first_name,
                    processed_last_name=processed_last_name,
                    customer_phone=customer_phone,  # type: ignore
                    unique_id=unique_id,
                    reservation_notes=reservation_notes,
                )
            except Exception as e:
                error_msg = str(e).lower()

                # Determine error prefix and try to show available options
                if "covers_value_out_of_range" in error_msg:
                    return f"This restaurant doesn't accept reservations for {party_size} people."
                elif "invalid_date_time_range" in error_msg:
                    return f"The date/time {date} at {time} is invalid."
                else:
                    return f"Unable to place a hold for {time} on {date} due to {error_msg}"

        except Exception as e:
            logger.debug(
                f"[YelpNoCreditCardTool]: make_reservation - Error: {e}, {traceback.format_exc()}"
            )
            if self._is_401_error(e):
                logger.debug(
                    "[YelpNoCreditCardTool]: make_reservation - 401 error detected, resetting cached token and retrying"
                )
                try:
                    return self._create_reservation_with_hold(
                        bearer_token=self._reset_and_refetch_token(),
                        party_size=party_size,
                        date=date,
                        time=time,
                        processed_first_name=processed_first_name,
                        processed_last_name=processed_last_name,
                        customer_phone=customer_phone,  # type: ignore
                        unique_id=unique_id,
                        reservation_notes=reservation_notes,
                    )
                except Exception as retry_e:
                    logger.debug(
                        f"[YelpNoCreditCardTool]: make_reservation - Retry failed: {str(retry_e)}"
                    )
                    return f"Failed to make reservation after retry. {str(retry_e)}"
            return f"Failed to make reservation. {str(e)}"

    @tool
    @params_validate()
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
                    "[YelpNoCreditCardTool]: get_waitlist_status - Failed to obtain Yelp bearer token"
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
                f"[YelpNoCreditCardTool]: get_waitlist_status - Error: {str(e)}, {traceback.format_exc()}"
            )
            if self._is_401_error(e):
                logger.debug(
                    "[YelpNoCreditCardTool]: get_waitlist_status - 401 error detected, resetting cached token and retrying"
                )
                try:
                    response = get_waitlist_status(
                        bearer_token=self._reset_and_refetch_token(),
                        business_id=self.business_id_or_alias,
                    )
                    return str(response)
                except Exception as retry_e:
                    logger.debug(
                        f"[YelpNoCreditCardTool]: get_waitlist_status - Retry failed: {str(retry_e)}"
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
            if cleaned.startswith("+") and len(digits_only) >= 10:
                normalized_phone = cleaned
            elif len(digits_only) == 10:
                normalized_phone = f"+1{digits_only}"
            elif len(digits_only) == 11 and digits_only.startswith("1"):
                normalized_phone = f"+{digits_only}"
            elif len(digits_only) >= 11:
                normalized_phone = f"+{digits_only}"
            else:
                return "Please provide a valid phone number for the waitlist."
        except Exception:
            return "Please provide a valid phone number for the waitlist."

        # Format party notes with Palona AI attribution
        party_notes = (
            f"Join waitlist via Palona AI: {notes.strip()}"
            if notes.strip()
            else "Join waitlist via Palona AI"
        )

        try:
            logger.debug(
                "[YelpNoCreditCardTool]: join_waitlist_queue - Starting waitlist queue join request"
            )
            bearer_token = self._yelp_bearer_token()

            # Validate bearer token before proceeding
            if not bearer_token:
                logger.debug(
                    "[YelpNoCreditCardTool]: join_waitlist_queue - Failed to obtain Yelp bearer token"
                )
                return "Unable to authenticate with Yelp. Please verify your API credentials."

            # Make API call to join waitlist queue
            logger.debug(
                "[YelpNoCreditCardTool]: join_waitlist_queue - Making API call to Yelp waitlist endpoint"
            )
            response = api_join_waitlist_queue(
                bearer_token=bearer_token,
                business_id=self.business_id_or_alias,
                phone=normalized_phone,
                party_size=party_size,
                name=name.strip(),
                party_notes=party_notes,
            )

            logger.debug(
                f"[YelpNoCreditCardTool]: join_waitlist_queue - API call successful - response: {response}"
            )

            return str(response)

        except Exception as e:
            logger.debug(
                f"[YelpNoCreditCardTool]: join_waitlist_queue - Error: {str(e)}, {traceback.format_exc()}"
            )
            if self._is_401_error(e):
                logger.debug(
                    "[YelpNoCreditCardTool]: join_waitlist_queue - 401 error detected, resetting cached token and retrying"
                )
                try:
                    # Reset cache and get fresh token, then retry
                    response = api_join_waitlist_queue(
                        bearer_token=self._reset_and_refetch_token(),
                        business_id=self.business_id_or_alias,
                        phone=normalized_phone,
                        party_size=party_size,
                        name=name.strip(),
                        party_notes=party_notes,
                    )
                    return str(response)
                except Exception as retry_e:
                    logger.debug(
                        f"[YelpNoCreditCardTool]: join_waitlist_queue - Retry failed: {str(retry_e)}"
                    )
                    return (
                        f"Failed to join the waitlist queue after retry. {str(retry_e)}"
                    )
            return f"Failed to join the waitlist queue. {str(e)}"
