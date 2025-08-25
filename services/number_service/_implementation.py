import os
from typing import Any, Dict, List, Optional

from twilio.rest import Client
from twilio.rest.api.v2010.account.incoming_phone_number import (
    IncomingPhoneNumberInstance,
)
from vapi import Vapi
from vapi.types.create_twilio_phone_number_dto import CreateTwilioPhoneNumberDto
from vapi.types.custom_llm_model import CustomLlmModel

from utils.log import logger

from ._utils import (
    AssistantConfig,
    NumberResponse,
    NumberType,
    UsageType,
    VerificationStatus,
)

RELEASED_LABEL = "RELEASED"
AVAILABLE_LABEL = "AVAILABLE"


class NumberService:
    """Service for managing phone numbers and Vapi assistants.

    This service provides functionality for:
    1. Purchasing and managing phone numbers through Twilio
    2. Creating and configuring Vapi assistants
    3. Integrating phone numbers with Vapi
    4. Handling both local and toll-free numbers

    Required environment variables:
        - TWILIO_ACCOUNT_SID: Twilio account identifier
        - TWILIO_AUTH_TOKEN: Twilio authentication token
        - VAPI_API_KEY: Vapi API key for assistant integration

    Example:
        ```python
        service = NumberService()

        # Purchase a toll-free number with assistant
        config = AssistantConfig(
            merchant_name="My Business",
            model_url="https://api.example.com/v1/",
            model_name="custom-model",
            server_url="https://webhook.example.com"
        )

        number = service.setup_number(
            country_code="US",
            toll_free=True,
            merchant_name="My Business",
            assistant_config=config
        )
        ```
    """

    def __init__(self):
        """Initialize the NumberService with required API clients.

        Sets up connections to both Twilio and Vapi services using credentials
        from environment variables. Validates that all required credentials
        are present before initialization.

        Raises:
            RuntimeError: If service initialization fails
            KeyError: If required environment variables are missing
        """
        try:
            # Retrieve each secret via public API
            twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
            twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
            vapi_token = os.environ.get("VAPI_API_KEY", "")

            # Validate that none are empty or None
            missing = [
                name
                for name, val in [
                    ("TWILIO_ACCOUNT_SID", twilio_account_sid),
                    ("TWILIO_AUTH_TOKEN", twilio_auth_token),
                    ("VAPI_API_KEY", vapi_token),
                ]
                if not val
            ]
            if missing:
                raise KeyError(f"Missing required secrets: {', '.join(missing)}")

            self.vapi_client = Vapi(token=vapi_token)
            self.twilio_client = Client(twilio_account_sid, twilio_auth_token)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize NumberService: {e}") from e

    def purchase_number(
        self,
        country_code: str,
        merchant_name: str,
        area_code: Optional[str] = None,
        contains: Optional[str] = None,
    ) -> NumberResponse:
        """Purchase a new local phone number from Twilio.

        Args:
            country_code: Two-letter country code (e.g., 'US')
            merchant_name: Business name to associate with the number
            area_code: Optional area code to search within (e.g., '415')
            contains: Optional pattern for substring matching in phone numbers

        Returns:
            NumberResponse containing the purchased number details

        Raises:
            ValueError: If no numbers are available or purchase fails
        """
        # Build search parameters for Twilio API
        list_params: Dict[str, Any] = {"limit": 1}
        if area_code:
            list_params["area_code"] = area_code
        if contains:
            list_params["contains"] = contains

        # Search for available numbers
        available_numbers = self.twilio_client.available_phone_numbers(
            country_code
        ).local.list(**list_params)

        if not available_numbers:
            criteria = [f"country_code={country_code}"]
            if area_code:
                criteria.append(f"area_code={area_code}")
            if contains:
                criteria.append(f"contains={contains}")
            raise ValueError(
                f"No available local phone numbers found for criteria: {', '.join(criteria)}"
            )

        number = available_numbers[0]
        try:
            twilio_number = self.twilio_client.incoming_phone_numbers.create(
                phone_number=number.phone_number,
                friendly_name=self._get_friendly_name(merchant_name, for_twilio=True),
            )
            if not twilio_number.phone_number:
                raise ValueError("Failed to get phone number from Twilio")
        except Exception as e:
            raise ValueError(f"Failed to purchase phone number: {e}") from e

        return NumberResponse(
            number=twilio_number.phone_number,
            merchant_name=merchant_name,
            country_code=country_code,
            toll_free=False,
        )

    def purchase_toll_free_number(
        self,
        country_code: str,
        merchant_name: str,
        contains: Optional[str] = None,
    ) -> NumberResponse:
        """Purchase a new toll-free phone number from Twilio.

        Args:
            country_code: Two-letter country code (e.g., 'US')
            merchant_name: Business name to associate with the number
            contains: Optional pattern for substring matching in phone numbers
                     Note: area_code is not applicable for toll-free numbers

        Returns:
            NumberResponse containing the purchased toll-free number details

        Raises:
            ValueError: If no toll-free numbers are available or purchase fails
        """
        # Build search parameters for Twilio API
        list_params: Dict[str, Any] = {"limit": 1}
        if contains:
            list_params["contains"] = contains

        # Search for available toll-free numbers
        available_numbers = self.twilio_client.available_phone_numbers(
            country_code
        ).toll_free.list(**list_params)

        if not available_numbers:
            criteria = [f"country_code={country_code}"]
            if contains:
                criteria.append(f"contains={contains}")
            raise ValueError(
                f"No available toll-free phone numbers found for criteria: {', '.join(criteria)}"
            )

        number = available_numbers[0]
        try:
            twilio_number = self.twilio_client.incoming_phone_numbers.create(
                phone_number=number.phone_number,
                friendly_name=self._get_friendly_name(merchant_name, for_twilio=True),
            )
            if not twilio_number.phone_number:
                raise ValueError("Failed to get toll-free phone number from Twilio")
        except Exception as e:
            raise ValueError(f"Failed to purchase toll-free phone number: {e}") from e

        return NumberResponse(
            number=twilio_number.phone_number,
            merchant_name=merchant_name,
            country_code=country_code,
            toll_free=True,
        )

    def _create_assistant_and_get_id(self, config: AssistantConfig) -> str:
        """Create a new Vapi assistant with custom model configuration.

        Args:
            config: Assistant configuration including model details and server URL

        Returns:
            Assistant instance configured with the specified model
        """
        assistant = self.vapi_client.assistants.create(
            name=config["merchant_name"],
            model=CustomLlmModel(url=config["model_url"], model=config["model_name"]),
        )
        return assistant.id

    def setup_number(
        self,
        country_code: str,
        toll_free: bool,
        merchant_name: str,
        assistant_config: Optional[AssistantConfig] = None,
        purchase_number: bool = False,
        area_code: Optional[str] = None,
        contains: Optional[str] = None,
    ) -> NumberResponse:
        """Set up a phone number with optional Vapi assistant integration.

        This method handles the complete setup process:
        1. Creates a Vapi assistant if configuration is provided
        2. Purchases a phone number (local or toll-free) or reuses approved numbers
        3. Integrates the number with Vapi
        4. Handles cleanup if any step fails

        Args:
            country_code: Two-letter country code (e.g., 'US')
            toll_free: Whether to purchase a toll-free number
            merchant_name: Business name to associate with the number
            assistant_config: Optional assistant configuration for Vapi integration
            purchase_number: If True, always purchase a new number. If False (default),
                           reuse approved numbers first, only purchasing if none available.
            area_code: Optional area code for local numbers (e.g., '415')
            contains: Optional pattern for number search (supports wildcards like '*6666')

        Returns:
            NumberResponse containing the set up number details

        Raises:
            ValueError: If number setup or integration fails
        """
        # Check if we should purchase a new number or reuse approved ones
        if purchase_number:
            # Force purchase a new number regardless of approved numbers
            phone_number = None
        else:
            # Try to reuse approved numbers first (existing behavior)
            approved_numbers = self.get_approved_numbers()
            phone_number = approved_numbers[0] if approved_numbers else None

        if phone_number is None:
            # Purchase number
            if toll_free:
                number_response = self.purchase_toll_free_number(
                    country_code, merchant_name, contains=contains
                )
            else:
                number_response = self.purchase_number(
                    country_code, merchant_name, area_code=area_code, contains=contains
                )

            if not number_response or not number_response.number:
                raise ValueError("Failed to get phone number from Twilio")
            phone_number = number_response.number
        else:
            # Reusing an approved number
            number_details = self.get_number_details(phone_number)
            if not number_details:
                raise ValueError("Failed to get phone number from Twilio")
            number_details.update(
                friendly_name=self._get_friendly_name(merchant_name, for_twilio=True)
            )
            number_response = NumberResponse(
                number=phone_number,
                merchant_name=self._get_friendly_name(merchant_name),
                country_code=country_code,
                toll_free=toll_free,
            )
        # Import number to Vapi
        try:
            self.vapi_client.phone_numbers.create(
                request=CreateTwilioPhoneNumberDto(
                    number=phone_number,
                    twilio_account_sid=self.twilio_client.username,  # type: ignore
                    twilio_auth_token=self.twilio_client.password,
                    name=self._get_friendly_name(merchant_name),
                ),
            )
        except Exception as e:
            self._release_number_from_twilio(
                phone_number
            )  # release the purchased number if the vapi call fails
            raise ValueError(f"Failed to import number to Vapi: {e}") from e

        return number_response

    # Batch purchase functionality removed - frontend handles multiple calls

    def get_purchased_numbers(self) -> List[IncomingPhoneNumberInstance]:
        """Retrieve all purchased phone numbers from Twilio for the current environment.

        Returns:
            List of Twilio IncomingPhoneNumberInstance objects for current environment:
            - phone_number: The actual number
            - friendly_name: Current display name matching current environment
            - sid: Twilio's unique identifier
        """
        # Get current environment
        env_lower = (os.environ.get("RUNTIME_ENV") or "dev").strip().lower()
        prefix = f"{env_lower}:"

        # Stream all numbers from Twilio, filtering by environment prefix
        filtered_numbers: list[IncomingPhoneNumberInstance] = []
        for number in self.twilio_client.incoming_phone_numbers.stream(limit=None):
            name_lower = str(number.friendly_name or "").lower()
            if name_lower.startswith(prefix):
                filtered_numbers.append(number)
        return filtered_numbers

    def get_purchased_numbers_by_page(
        self,
        page: int = 0,
        page_size: int = 20,
        friendly_name: str | None = None,
        phone_number: str | None = None,
    ) -> tuple[List[IncomingPhoneNumberInstance], bool]:
        """
        Retrieve purchased phone numbers with efficient native filtering and pagination.

        Uses Twilio's native list() method with filtering and pagination for optimal performance.

        Args:
            page: Page number (0-based indexing, default: 0)
            page_size: Number of numbers per page (default: 20, max: 100)
            friendly_name: Optional friendly name to filter by (exact match with env prefix)
            phone_number: Optional phone number to filter by (exact match)

        Returns:
            Tuple containing:
            - List of Twilio IncomingPhoneNumberInstance objects
            - Boolean indicating if there are more pages available

        Raises:
            ValueError: If page or page_size parameters are invalid
        """
        # Validate parameters
        if page < 0:
            raise ValueError("page must be >= 0")
        if not (1 <= page_size <= 100):
            raise ValueError("page_size must be between 1 and 100")

        # Get current environment (raw + lower) for different matching needs
        stage_raw = (os.environ.get("RUNTIME_ENV") or "dev").strip()
        env_lower = stage_raw.lower()

        try:
            # Unified streaming approach for all filtering scenarios
            env_prefix = f"{env_lower}:"

            # Create single reusable environment filter function
            def env_filter(num):
                return str(num.friendly_name or "").lower().startswith(env_prefix)

            if phone_number is not None:
                # Scenario 3: Hybrid phone number filtering (native + environment check)
                return self._get_filtered_numbers_with_streaming(
                    filter_func=env_filter,  # Reuse env_filter (same logic as phone_env_filter)
                    page=page,
                    page_size=page_size,
                    filter_value=phone_number,
                    native_filter_type="phone_number",
                )

            elif friendly_name is not None:
                # Scenario 2: Native friendly name filtering (no additional filtering needed)
                target_friendly_name = f"{stage_raw}:{friendly_name}"
                return self._get_filtered_numbers_with_streaming(
                    filter_func=None,  # No additional filtering needed (Twilio already filtered exactly)
                    page=page,
                    page_size=page_size,
                    filter_value=target_friendly_name,
                    native_filter_type="friendly_name",
                )

            else:
                # Scenario 1: Environment-only filtering (pure streaming)
                return self._get_filtered_numbers_with_streaming(
                    filter_func=env_filter,  # Reuse same env_filter
                    page=page,
                    page_size=page_size,
                    filter_value=env_prefix,
                    native_filter_type="environment",
                )

        except Exception as e:
            logger.error(f"Error in get_purchased_numbers_by_page: {e}")
            raise ValueError(f"Failed to fetch numbers from Twilio: {e}")

    def _get_filtered_numbers_with_streaming(
        self,
        filter_func,
        page: int,
        page_size: int,
        filter_value: str,
        native_filter_type: str,
    ) -> tuple[List[IncomingPhoneNumberInstance], bool]:
        """
        Unified streaming-based pagination for all filtering scenarios.

        This method provides consistent, memory-efficient pagination for:
        1. Phone number filtering (hybrid: native Twilio + environment check) - HIGHEST PRIORITY
        2. Friendly name filtering (hybrid: native Twilio filtering, no additional filtering needed)
        3. Environment-only filtering (pure streaming with client-side filtering)

        Features:
        - Memory efficient streaming (loads chunks, not all data)
        - Early termination (stops when enough results found)
        - Automatic native filtering optimization based on filter type
        - Consistent pagination across all scenarios

        Args:
            filter_func: Function to filter individual numbers (None if no additional filtering needed)
            page: Page number (0-based)
            page_size: Items per page
            filter_value: Value being filtered for logging
            native_filter_type: Type of filtering ('environment', 'friendly_name', 'phone_number')

        Returns:
            Tuple of (filtered_numbers, has_more)
        """
        matched: list[IncomingPhoneNumberInstance] = []
        target_start = page * page_size
        target_end_exclusive = target_start + page_size
        max_needed = target_end_exclusive + 1  # +1 to determine has_more

        try:
            # Log the filtering operation
            logger.info(
                f"Filtering phone numbers: type={native_filter_type}, filter_value='{filter_value}', page={page}"
            )

            # Build unified streaming parameters
            params = {
                "limit": None,
                "page_size": 50,  # Optimal chunk size for memory efficiency
            }

            # Add native filter parameter based on type
            if native_filter_type == "phone_number":
                # Scenario 1: Native phone_number filtering + environment check (HIGHEST PRIORITY)
                params["phone_number"] = filter_value
            elif native_filter_type == "friendly_name":
                # Scenario 2: Native friendly_name filtering (no additional filtering needed)
                params["friendly_name"] = filter_value
            elif native_filter_type == "environment":
                # Scenario 3: Pure streaming with environment filtering (no native filter params)
                pass  # No additional params needed
            else:
                raise ValueError(
                    f"Unsupported native_filter_type: {native_filter_type}"
                )

            # Unified streaming with conditional filtering logic
            processed_count = 0
            for num in self.twilio_client.incoming_phone_numbers.stream(**params):
                processed_count += 1

                # Apply conditional filtering based on scenario
                should_include = False
                if native_filter_type == "friendly_name":
                    # No additional filtering needed - Twilio already filtered exactly
                    should_include = True
                elif native_filter_type in ["phone_number", "environment"]:
                    # Apply environment check for both phone number and environment scenarios
                    should_include = filter_func(num) if filter_func else True

                if should_include:
                    matched.append(num)
                    if len(matched) >= max_needed:
                        logger.info(
                            f"Early termination: found {len(matched)} results, processing stopped"
                        )
                        break

            # Extract the requested page
            page_numbers = matched[target_start:target_end_exclusive]
            has_more = len(matched) > target_end_exclusive

            logger.info(
                f"Page {page} complete: {len(page_numbers)} numbers returned (total_matched={len(matched)}, has_more={has_more})"
            )
            return page_numbers, has_more

        except Exception as e:
            logger.error(f"Error in streaming {native_filter_type} filtering: {e}")
            raise ValueError(f"Failed to filter numbers by {native_filter_type}: {e}")

    def get_number_details(self, number: str) -> IncomingPhoneNumberInstance | None:
        """Get details of a specific purchased phone number.

        Args:
            number: The phone number to look up

        Returns:
            IncomingPhoneNumberInstance if found, None otherwise
        """
        numbers = self.twilio_client.incoming_phone_numbers.list(phone_number=number)
        if not numbers:
            return None
        return numbers[0]

    def _release_number_from_vapi(self, number: str):
        """Release a phone number from Vapi integration.

        Args:
            number: The phone number to release

        Raises:
            ValueError: If release from Vapi fails
        """
        try:

            vapi_numbers = self.vapi_client.phone_numbers.list()
            for n in vapi_numbers:
                if n.number == number:
                    self.vapi_client.phone_numbers.delete(id=n.id)
                    break
        except Exception as e:
            raise ValueError(f"Failed to release number from Vapi: {e}") from e

    def _release_number_from_twilio(self, number: str):
        """Release a phone number from Twilio (marks as RELEASED, keeps number).

        Args:
            number: The phone number to release

        Raises:
            ValueError: If number not found or release fails
        """
        try:
            numbers = self.twilio_client.incoming_phone_numbers.list(
                phone_number=number
            )
            if not numbers:
                logger.warn("Phone number does not exist in twilio, skipping deletion.")
                return
            for n in numbers:
                if n.phone_number == number:
                    if n.friendly_name and "INACTIVATED" in n.friendly_name:
                        n.delete()
                    else:

                        n.update(friendly_name=self._get_friendly_name(RELEASED_LABEL))
                    break
        except Exception as e:
            raise ValueError(f"Failed to release number from Twilio: {e}") from e

    def _delete_number_from_twilio(self, number: str):
        """Completely delete a phone number from Twilio account.

        Args:
            number: The phone number to delete

        Raises:
            ValueError: If number not found or deletion fails
        """
        try:
            numbers = self.twilio_client.incoming_phone_numbers.list(
                phone_number=number
            )
            if not numbers:
                logger.warn("Phone number does not exist in twilio, skipping deletion.")
                return
            for n in numbers:
                if n.phone_number == number:
                    n.delete()  # Actually delete the number completely
                    logger.info(f"Successfully deleted number {number} from Twilio")
                    break
        except Exception as e:
            raise ValueError(f"Failed to delete number from Twilio: {e}") from e

    def delete_number(self, number: str):
        """Completely delete a phone number from both Vapi and Twilio.

        This method ensures complete deletion by:
        1. Removing the number from Vapi integration
        2. Deleting the number from Twilio (not just marking as released)

        Args:
            number: The phone number to delete

        Raises:
            ValueError: If deletion from either service fails
        """
        self._release_number_from_vapi(number)
        self._delete_number_from_twilio(number)

    def activate_number(self, number: str):
        """Manually activate a phone number from after it has been verified by Twilio.

        Args:
            number: The phone number to activate
        """
        number_details = self.get_number_details(number)
        if not number_details or not number_details.friendly_name:
            raise ValueError("Number not found")
        if "INACTIVATED" in number_details.friendly_name:
            number_details.update(
                friendly_name=number_details.friendly_name.replace("_INACTIVATED", "")
            )
        else:
            raise ValueError("Number is already activated")

    def release_number(self, number: str):
        """Release a phone number from both Vapi and Twilio.

        This method ensures complete cleanup by:
        1. Removing the number from Vapi integration
        2. Releasing the number from Twilio

        Args:
            number: The phone number to release

        Raises:
            ValueError: If release from either service fails
        """
        self._release_number_from_vapi(number)
        self._release_number_from_twilio(number)

    def _get_friendly_name(self, name: str, for_twilio: bool = False) -> str:
        stage = os.environ.get("RUNTIME_ENV") or "dev"
        # twilio limits friendly name to max of 40 chars
        # here we will take the last n chars of a name
        # so it doesn't exceed 40 with the env label. Why last n
        # instead of first n? The last n is better at identifying
        # the project than the first n chars.
        if for_twilio:
            prefix_length = len(stage) + 1
            name_length = 40 - prefix_length
            name = name[-name_length:]
        return f"{stage}:{name}"

    def _get_phone_number_type(self, phone_number: str) -> NumberType:
        """
        Get the type of a phone number using prefix-based detection.

        Uses the official North American Numbering Plan (NANPA) toll-free prefixes
        managed by the FCC to determine if a number is toll-free.

        Args:
            phone_number: The phone number to check (in E.164 format)

        Returns:
            NumberType: TOLL_FREE if it's a toll-free number, OTHER otherwise
        """
        if not phone_number:
            return NumberType.OTHER

        # Remove +1 country code if present and check US/Canada toll-free prefixes
        clean_number = phone_number.replace("+1", "").replace("-", "").replace(" ", "")

        # Official North American toll-free prefixes (FCC/NANPA managed)
        toll_free_prefixes = ["800", "833", "844", "855", "866", "877", "888"]

        for prefix in toll_free_prefixes:
            if clean_number.startswith(prefix):
                return NumberType.TOLL_FREE

        return NumberType.OTHER

    def get_toll_free_verification_status(
        self, number_sid: str
    ) -> VerificationStatus | None:
        """
        Get the toll-free verification status for a specific phone number.

        Args:
            number_sid: The Twilio SID of the phone number

        Returns:
            VerificationStatus: The verification status enum or None if no verification found
        """
        try:
            tollfree_verifications = (
                self.twilio_client.messaging.v1.tollfree_verifications.list(
                    tollfree_phone_number_sid=number_sid, limit=1
                )
            )
            if tollfree_verifications:
                status_str = str(tollfree_verifications[0].status)
                # Map Twilio status to our enum
                status_mapping = {
                    "IN_REVIEW": VerificationStatus.IN_REVIEW,
                    "TWILIO_APPROVED": VerificationStatus.TWILIO_APPROVED,
                }
                return status_mapping.get(status_str, VerificationStatus.UNVERIFIED)
            return None
        except Exception as e:
            logger.warning(
                f"Failed to get toll-free verification status for {number_sid}: {e}"
            )
            return None

    def get_available_numbers(self):
        """
        Get available numbers with their verification status.

        NOTE: Reverted to original implementation as requested - this only includes
        toll-free numbers that have verification records, not all toll-free numbers.
        """
        number_pool = {}
        numlist = self.twilio_client.incoming_phone_numbers.list()
        for num in numlist:
            if not num.friendly_name:
                continue
            tollfree_verifications = (
                self.twilio_client.messaging.v1.tollfree_verifications.list(
                    tollfree_phone_number_sid=num.sid, limit=1
                )
            )
            for record in tollfree_verifications:
                number_pool[num.phone_number] = {
                    "friendly_name": num.friendly_name,
                    "status": str(record.status),
                }
        return number_pool

    def get_approved_numbers(self):
        number_pool = self.get_available_numbers()
        approved_numbers = []
        released_name = self._get_friendly_name(RELEASED_LABEL)
        for number, name_statue in number_pool.items():
            if (
                "approved" in name_statue["status"].lower()
                and name_statue["friendly_name"] == released_name
            ):
                approved_numbers.append(number)
        return approved_numbers

    def get_rejected_numbers(self):
        number_pool = self.get_available_numbers()
        rejected_numbers = []
        for number, name_statue in number_pool.items():
            if "rejected" in name_statue["status"].lower():
                rejected_numbers.append(number)
        return rejected_numbers

    def get_inreview_numbers(self):
        number_pool = self.get_available_numbers()
        inreview_numbers = []
        for number, name_statue in number_pool.items():
            if "review" in name_statue["status"].lower():
                inreview_numbers.append(number)
        return inreview_numbers

    def list_phone_numbers_with_details(
        self,
        session,
        page: int = 1,
        page_size: int = 20,
        friendly_name: str | None = None,
        phone_number: str | None = None,
    ):
        """
        Business logic for listing phone numbers with full details including project associations.

        This method handles:
        - Retrieving paginated phone numbers from Twilio with native filtering
        - Determining phone number types (toll-free vs other)
        - Checking toll-free verification status
        - Finding associated projects and accounts
        - Determining usage types (voice/sms/both/unused)
        - Optional filtering by exact friendly name or phone number match

        Args:
            session: Database session for project lookups
            page: Page number (1-based)
            page_size: Number of items per page
            friendly_name: Optional friendly name to filter by (exact match with env prefix)
            phone_number: Optional phone number to filter by (exact match)

        Returns:
            tuple: (phone_numbers_data, has_more) where phone_numbers_data is a list of dicts
                   containing all the processed phone number information
        """
        from services import project_service

        # Get purchased numbers from Twilio with pagination (convert to 0-based)
        twilio_numbers, has_more = self.get_purchased_numbers_by_page(
            page=page - 1,
            page_size=page_size,
            friendly_name=friendly_name,
            phone_number=phone_number,
        )

        # Process each phone number with business logic
        phone_numbers_data = []
        for twilio_number in twilio_numbers:
            # Validate required fields from Twilio
            phone_number = twilio_number.phone_number
            sid = twilio_number.sid
            if not phone_number or not sid:
                logger.warning(
                    "Skipping Twilio number with missing identifiers",
                    extra={"sid": sid, "phone_number": phone_number},
                )
                continue

            # Determine phone number type
            number_type = self._get_phone_number_type(phone_number)

            # Check verification status for toll-free numbers
            status = None
            if number_type == NumberType.TOLL_FREE:
                status = self.get_toll_free_verification_status(sid)
                if status is None:
                    status = VerificationStatus.UNVERIFIED

            # Find associated projects and accounts
            projects = project_service.get_projects_by_phone_number(
                session, phone_number
            )

            # Determine usage type by checking channel identifiers
            usage_types = set()
            for project in projects:
                for channel_identifier in project.channel_identifiers or []:
                    clean_identifier = channel_identifier.strip()
                    if clean_identifier.endswith(f":{phone_number}"):
                        channel_type = clean_identifier.split(":")[0]
                        if channel_type in ["voice", "sms"]:
                            usage_types.add(channel_type)

            # Determine overall usage type
            if not usage_types:
                usage_type = UsageType.UNUSED
            elif len(usage_types) == 1:
                channel_type = list(usage_types)[0]
                usage_type = (
                    UsageType.VOICE if channel_type == "voice" else UsageType.SMS
                )
            else:
                usage_type = UsageType.BOTH

            # Extract project and account information
            project_ids = [project.id for project in projects] if projects else None
            project_names = [project.name for project in projects] if projects else None
            account_ids = (
                [project.account_id for project in projects] if projects else None
            )
            account_names = (
                [project.account.name for project in projects] if projects else None
            )

            # Build processed phone number data
            phone_number_data = {
                "phone_number": phone_number,
                "friendly_name": twilio_number.friendly_name,
                "sid": sid,
                "status": status,
                "project_ids": project_ids,
                "project_names": project_names,
                "account_ids": account_ids,
                "account_names": account_names,
                "usage_type": usage_type,
                "number_type": number_type,
            }
            phone_numbers_data.append(phone_number_data)

        return phone_numbers_data, has_more
