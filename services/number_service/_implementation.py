import os
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from twilio.rest import Client
from twilio.rest.api.v2010.account.incoming_phone_number import (
    IncomingPhoneNumberInstance,
)

from db.repositories.project_repository import ProjectRepository
from utils.log import logger

from ._utils import (
    NumberChannel,
    NumberResponse,
    NumberType,
    UsageType,
    VerificationStatus,
)

RELEASED_LABEL = "RELEASED"
AVAILABLE_LABEL = "AVAILABLE"


class NumberService:
    """Service for managing phone numbers with LiveKit voice routing.

    This service provides functionality for:
    1. Purchasing and managing phone numbers through Twilio
    2. Configuring phone numbers with LiveKit SIP trunk routing
    3. Handling both local and toll-free numbers

    Required environment variables:
        - TWILIO_ACCOUNT_SID: Twilio account identifier
        - TWILIO_AUTH_TOKEN: Twilio authentication token
        - TWILIO_SIP_TRUNK_SID: SIP trunk for LiveKit voice routing

    Example:
        ```python
        service = NumberService()

        # Purchase a toll-free number
        number = service.setup_number(
            country_code="US",
            toll_free=True,
            purchase_number=True,
            merchant_name="My Business"
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

            # Validate that none are empty or None
            missing = [
                name
                for name, val in [
                    ("TWILIO_ACCOUNT_SID", twilio_account_sid),
                    ("TWILIO_AUTH_TOKEN", twilio_auth_token),
                ]
                if not val
            ]
            if missing:
                raise KeyError(f"Missing required secrets: {', '.join(missing)}")

            self.twilio_client = Client(twilio_account_sid, twilio_auth_token)
            self._twilio_sip_trunk_sid = os.environ.get("TWILIO_SIP_TRUNK_SID")
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
            sid=twilio_number.sid,
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
            sid=twilio_number.sid,
            number=twilio_number.phone_number,
            merchant_name=merchant_name,
            country_code=country_code,
            toll_free=True,
        )

    def _setup_number_for_livekit(
        self,
        phone_number: str,
    ) -> None:
        """Configure a Twilio number for LiveKit SIP routing.

        Sets the trunk_sid on the Twilio number so inbound calls are
        forwarded via SIP to LiveKit. A shared callee dispatch rule on
        LiveKit handles per-number routing automatically.
        """
        if not self._twilio_sip_trunk_sid:
            raise ValueError(
                "TWILIO_SIP_TRUNK_SID env var is required for LiveKit provisioning."
            )

        number_details = self.get_number_details(phone_number)
        if not number_details:
            raise ValueError(f"Phone number {phone_number} not found in Twilio")

        try:
            number_details.update(trunk_sid=self._twilio_sip_trunk_sid)
        except Exception as e:
            raise ValueError(
                f"Failed to assign Twilio SIP trunk to {phone_number}: {e}"
            ) from e

        logger.info(
            f"Phone number {phone_number} assigned to SIP trunk for LiveKit",
            extra={"phone_number": phone_number},
        )

    def _release_number_from_livekit(
        self,
        phone_number: str,
    ) -> None:
        """Remove LiveKit SIP routing from a Twilio number.

        Clears the trunk_sid so Twilio stops forwarding calls via SIP.
        """
        try:
            number_details = self.get_number_details(phone_number)
            if number_details:
                number_details.update(trunk_sid="")
            logger.info(
                f"Phone number {phone_number} released from LiveKit SIP trunk",
                extra={"phone_number": phone_number},
            )
        except Exception as e:
            logger.warning(f"Failed to clear Twilio trunk for {phone_number}: {e}")

    def _is_number_on_livekit(self, phone_number: str) -> bool:
        """Check if a phone number is routed through LiveKit.

        Returns True if the Twilio number has a SIP trunk assigned.
        """
        number_details = self.get_number_details(phone_number)
        if not number_details:
            return False
        return bool(getattr(number_details, "trunk_sid", None))

    def setup_number(
        self,
        country_code: str,
        toll_free: bool,
        merchant_name: str,
        purchase_number: bool = False,
        area_code: Optional[str] = None,
        contains: Optional[str] = None,
        voice_provider: str = "livekit",
    ) -> NumberResponse:
        """Set up a phone number with LiveKit voice routing.

        This method handles the complete setup process:
        1. Purchases a phone number (local or toll-free) or reuses approved numbers
        2. Configures the number with LiveKit SIP trunk routing
        3. Handles cleanup if any step fails

        Args:
            country_code: Two-letter country code (e.g., 'US')
            toll_free: Whether to purchase a toll-free number
            merchant_name: Business name to associate with the number
            purchase_number: If True, always purchase a new number. If False (default),
                           reuse approved numbers first, only purchasing if none available.
            area_code: Optional area code for local numbers (e.g., '415')
            contains: Optional pattern for number search (supports wildcards like '*6666')
            voice_provider: Voice provider to use (default: 'livekit')

        Returns:
            NumberResponse containing the set up number details

        Raises:
            ValueError: If number setup or integration fails, or if unsupported voice provider
        """
        # Validate voice provider
        if voice_provider != "livekit":
            raise ValueError(
                f"Unsupported voice provider: {voice_provider}. Only 'livekit' is currently supported."
            )

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
                # Add the purchased number to messaging service
                if number_response.sid is None:
                    raise ValueError("Phone number SID is not valid")
                self._add_number_to_messaging_service(
                    number_response.sid,
                    number_response.number,
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
                sid=number_details.sid,
                number=phone_number,
                merchant_name=self._get_friendly_name(merchant_name),
                country_code=country_code,
                toll_free=toll_free,
            )
        # Setup LiveKit voice routing
        try:
            self._setup_number_for_livekit(phone_number)
        except Exception as e:
            self._delete_number_from_twilio(phone_number)
            raise ValueError(f"Failed to provision number for LiveKit: {e}") from e

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
                        break

            # Extract the requested page
            page_numbers = matched[target_start:target_end_exclusive]
            has_more = len(matched) > target_end_exclusive
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

    def reserve_existing_number(
        self,
        phone_number: str,
        merchant_name: str,
        session: Session,
        voice_provider: str = "livekit",
    ) -> bool:
        """Reserve an existing phone number for a project.

        This method validates that the phone number exists and is available for assignment,
        then updates its friendly name to associate it with the project.

        Args:
            phone_number: The existing phone number to reserve
            merchant_name: The project name to associate with the number
            session: Database session for project lookups

        Returns:
            True if the number was successfully reserved

        Raises:
            ValueError: If the number doesn't exist, is not available, or reservation fails
        """
        # Get the existing number details
        number_details = self.get_number_details(phone_number)
        if not number_details:
            raise ValueError(f"Phone number {phone_number} not found in Twilio account")

        if self._is_number_associated_with_project(phone_number, session):
            raise ValueError(
                f"Phone number {phone_number} is already associated with a project and not available for assignment"
            )

        # Ensure existing pool numbers are ready for LiveKit before assignment.
        if voice_provider == "livekit" and not getattr(
            number_details, "trunk_sid", None
        ):
            self._setup_number_for_livekit(phone_number)

        try:
            # Update the friendly name to associate with the project
            new_friendly_name = self._get_friendly_name(merchant_name, for_twilio=True)
            number_details.update(friendly_name=new_friendly_name)

            return True

        except Exception as e:
            # Rollback: restore original friendly name to make number available again
            self._set_number_available(phone_number)

            raise ValueError(
                f"Failed to reserve existing number {phone_number}: {e}"
            ) from e

    def assign_phone_number_to_project(
        self,
        project_id: uuid.UUID,
        project_name: str,
        channels: List[NumberChannel],
        session,
        context,
        phone_number: Optional[str] = None,
        country_code: str = "US",
        toll_free: bool = True,
        auto_commit: bool = True,
        voice_provider: str = "livekit",
    ) -> str:
        """Assign a phone number to a project with complete channel setup.

        This method handles the complete workflow of either purchasing a new number
        or reserving an existing number, then updating the project's channel identifiers.

        Args:
            project_id: ID of the project to assign the number to
            project_name: Name of the project (for friendly naming)
            channels: List of channels (voice, sms) the number will be used for
            session: Database session for project operations
            context: User context for project updates
            phone_number: Optional existing phone number to reserve (if None, purchases new)
            country_code: Country code for new numbers (default: "US")
            toll_free: Whether new numbers should be toll-free (default: True)
            voice_provider: Voice routing provider (default: 'livekit')

        Returns:
            str: The phone number that was assigned to the project

        Raises:
            ValueError: If number reservation/purchase fails or channel update fails
        """
        assigned_phone_number = None

        try:
            if phone_number:
                # Reserve existing number
                success = self.reserve_existing_number(
                    phone_number=phone_number,
                    merchant_name=project_name,
                    session=session,
                    voice_provider=voice_provider,
                )
                if not success:
                    raise ValueError(
                        f"Failed to reserve existing number {phone_number}"
                    )

                assigned_phone_number = phone_number

            else:
                # Purchase new number
                number_response = self.setup_number(
                    country_code=country_code,
                    toll_free=toll_free,
                    merchant_name=project_name,
                    purchase_number=True,
                    voice_provider=voice_provider,
                )
                assigned_phone_number = number_response.number

            # Update project channel identifiers
            self._modify_project_channels(
                project_id=project_id,
                session=session,
                context=context,
                modification_fn=lambda existing_channels: existing_channels
                + [f"{channel.value}:{assigned_phone_number}" for channel in channels],
                log_message=f"Added phone number {assigned_phone_number} to project channels",
                phone_number=assigned_phone_number,
                channels=channels,
                auto_commit=auto_commit,
            )

            logger.info(
                f"Phone number assigned to project: {assigned_phone_number}",
                extra={"project_id": project_id, "phone_number": assigned_phone_number},
            )

            return assigned_phone_number

        except Exception as e:
            # Rollback: handle cleanup based on what was assigned
            if assigned_phone_number:
                self._rollback_phone_number_assignment(
                    assigned_phone_number, phone_number is not None
                )

            raise ValueError(f"Failed to assign phone number to project: {e}") from e

    def _modify_project_channels(
        self,
        project_id: uuid.UUID,
        session,
        context,
        modification_fn,
        log_message: str,
        phone_number: Optional[str] = None,
        channels: Optional[List[NumberChannel]] = None,
        auto_commit: bool = True,
    ):
        """Generic method to modify project channel identifiers.

        Args:
            project_id: ID of the project to update
            session: Database session
            context: User context for the update (not used by repository but kept for API compatibility)
            modification_fn: Function that takes current channels list and returns modified list
            log_message: Message to log on successful update
            phone_number: Optional phone number for logging context
            channels: Optional channels list for logging context
            auto_commit: Whether to commit changes immediately (default: True)

        Raises:
            ValueError: If project not found or update fails
        """
        # Get current project using repository
        project_repo = ProjectRepository(session, auto_commit=auto_commit)
        project = project_repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project with id {project_id} not found")

        # Apply modification function to current channels
        current_channels = list(project.channel_identifiers or [])
        new_channels = modification_fn(current_channels)

        # Update project with modified channel identifiers using repository
        updated_project = project_repo.update_project(
            project_id=project_id,
            channel_identifiers=new_channels,
        )
        if not updated_project:
            raise ValueError(f"Failed to update project {project_id}")

        # Build logging context
        log_extra = {
            "project_id": project_id,
            "total_channels": len(new_channels),
            "changed_count": len(new_channels) - len(current_channels),
        }
        if phone_number:
            log_extra["phone_number"] = phone_number
        if channels:
            log_extra["new_channels"] = [ch.value for ch in channels]

        logger.info(log_message, extra=log_extra)

    def _rollback_phone_number_assignment(self, phone_number: str, was_existing: bool):
        """Rollback phone number assignment on failure.

        Args:
            phone_number: Phone number to rollback
            was_existing: True if it was an existing number (rollback to AVAILABLE),
                         False if it was new (release completely)
        """
        try:
            if was_existing:
                # For existing numbers, set back to AVAILABLE
                logger.warning(
                    f"Rolling back existing number assignment: {phone_number}",
                    extra={"phone_number": phone_number, "action": "set_available"},
                )
                self._set_number_available(phone_number)
            else:
                # For new numbers, release completely
                logger.warning(
                    f"Rolling back new number assignment: {phone_number}",
                    extra={"phone_number": phone_number, "action": "complete_release"},
                )
                self.delete_number(phone_number)

        except Exception as rollback_error:
            logger.exception(
                f"Failed to rollback phone number {phone_number}",
                extra={
                    "phone_number": phone_number,
                    "was_existing": was_existing,
                    "rollback_error": str(rollback_error),
                },
            )

    def release_phone_number_from_project(
        self,
        project_id: uuid.UUID,
        phone_number: str,
        release_type: Any,  # Enum or string
        session,
        context,
        auto_commit: bool = True,
    ) -> str:
        """Release a phone number from a project with complete validation and cleanup.

        This method handles the complete workflow of releasing a phone number from a project:
        1. Validates the phone number belongs to the project
        2. Releases the number using the specified release type
        3. Updates the project's channel identifiers to remove the number

        Args:
            project_id: ID of the project to release the number from
            phone_number: Phone number to release
            release_type: Either 'return_to_pool' or 'delete_permanently' (str or Enum)
            session: Database session for project operations
            context: User context for project updates
            auto_commit: Whether to commit changes immediately (default: True)

        Returns:
            str: Success message describing what was done

        Raises:
            ValueError: If phone number doesn't belong to project or release fails
        """
        # Step 1: Validate phone number ownership
        self._validate_phone_number_ownership(project_id, phone_number, session)

        # Step 2: Release the phone number using existing service method
        self.release_number_with_options(
            phone_number=phone_number, release_type=release_type
        )

        # Step 3: Remove phone number from project channels
        self._modify_project_channels(
            project_id=project_id,
            session=session,
            context=context,
            modification_fn=lambda channels: [
                ch
                for ch in channels
                if not (
                    ch.split(":")[0] in ["sms", "voice"]
                    and ch.split(":")[1] == phone_number
                )
            ],
            log_message=f"Removed phone number {phone_number} from project channels",
            phone_number=phone_number,
            auto_commit=auto_commit,
        )

        # Step 4: Generate success message based on release type
        release_type_value = getattr(release_type, "value", release_type)

        if release_type_value == "return_to_pool":
            message = f"Phone number {phone_number} has been returned to the available pool and can be reused"
        else:  # delete_permanently - only other valid option
            message = f"Phone number {phone_number} has been permanently deleted from Twilio and Vapi"

        logger.info(
            f"Phone number released from project: {phone_number} ({release_type_value})",
            extra={"project_id": project_id, "phone_number": phone_number},
        )

        return message

    def _validate_phone_number_ownership(
        self, project_id: uuid.UUID, phone_number: str, session
    ):
        """Validate that a phone number belongs to the specified project.

        Args:
            project_id: ID of the project to check
            phone_number: Phone number to validate
            session: Database session

        Raises:
            ValueError: If project not found or phone number doesn't belong to project
        """
        # Get project details using repository
        project_repo = ProjectRepository(session, auto_commit=False)
        project = project_repo.get_project(project_id)
        if not project:
            raise ValueError(f"Project with id {project_id} not found")

        # Extract phone numbers from project channels
        project_phone_numbers = set(
            [
                channel_identifier.split(":")[1]
                for channel_identifier in project.channel_identifiers or []
                if channel_identifier.split(":")[0] in ["sms", "voice"]
            ]
        )

        if phone_number not in project_phone_numbers:
            raise ValueError(
                f"Phone number {phone_number} does not belong to project {project_id}"
            )

    def _set_number_available(self, phone_number: str):
        """Set phone number friendly name to AVAILABLE for reuse.

        This method handles both rollback scenarios and explicit "return to pool" operations
        by setting the number's friendly name to AVAILABLE in Twilio.

        Args:
            phone_number: The phone number to mark as available

        Raises:
            ValueError: If update fails
        """
        try:
            number_details = self.get_number_details(phone_number)
            if number_details:
                available_name = self._get_friendly_name(
                    AVAILABLE_LABEL, for_twilio=True
                )
                number_details.update(friendly_name=available_name)

        except Exception as e:
            logger.warning(
                f"Failed to rollback reservation for number {phone_number}: {e}",
                extra={"phone_number": phone_number},
            )

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
                logger.warning(
                    "Phone number does not exist in twilio, skipping deletion."
                )
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
                logger.warning(
                    "Phone number does not exist in twilio, skipping deletion."
                )
                return
            for n in numbers:
                if n.phone_number == number:
                    n.delete()  # Actually delete the number completely
                    break
        except Exception as e:
            raise ValueError(f"Failed to delete number from Twilio: {e}") from e

    def delete_number(self, number: str):
        """Completely delete a phone number from LiveKit and Twilio.

        This method ensures complete deletion by:
        1. Checking if number is on LiveKit (via API)
        2. Removing the number from LiveKit if provisioned
        3. Deleting the number from Twilio (not just marking as released)

        Args:
            number: The phone number to delete

        Raises:
            ValueError: If deletion from either service fails
        """
        if self._is_number_on_livekit(number):
            self._release_number_from_livekit(number)
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
        """Release a phone number from Twilio.

        This method releases the number from Twilio by marking it as RELEASED.

        Args:
            number: The phone number to release

        Raises:
            ValueError: If release from Twilio fails
        """
        self._release_number_from_twilio(number)

    def release_number_with_options(self, phone_number: str, release_type: Any):
        """Release a phone number with specified handling options.

        This method provides enhanced control over how phone numbers are handled after release:
        - 'return_to_pool': Keeps in Twilio but releases from voice provider, sets friendly name to AVAILABLE
        - 'delete_permanently': Completely removes from both voice provider and Twilio

        Args:
            phone_number: The phone number to release
            release_type: Either 'return_to_pool' or 'delete_permanently' (str or Enum)

        Raises:
            ValueError: If release fails or invalid release_type
        """
        # Coerce Enum to its value; accept raw strings as-is
        release_type_value = getattr(release_type, "value", release_type)

        if release_type_value == "return_to_pool":
            # For LiveKit numbers, clean up dispatch rule before returning to pool
            if self._is_number_on_livekit(phone_number):
                self._release_number_from_livekit(phone_number)
            self._set_number_available(phone_number)

        elif release_type_value == "delete_permanently":
            # Use existing complete deletion logic
            self.delete_number(phone_number)

        else:
            raise ValueError(
                f"Invalid release_type: {release_type_value}. Must be 'return_to_pool' or 'delete_permanently'"
            )

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

    def _add_number_to_messaging_service(
        self, phone_number_sid: str, phone_number: str
    ):
        """Add a phone number to the appropriate Twilio messaging service based on environment.

        This method adds the phone number to the messaging service corresponding to the current
        runtime environment. If the operation fails, it logs a warning but does not raise an
        exception to avoid interrupting the main workflow.

        Args:
            phone_number: The phone number to add to the messaging service
        """
        try:
            # Get the messaging service SID for this environment
            messaging_service_sid = os.environ.get("MESSAGING_SERVICE_SID")
            if not messaging_service_sid:
                logger.warning(
                    "No messaging service SID configured",
                    extra={"phone_number": phone_number},
                )
                return

            # Add the phone number to the messaging service
            messaging_phone_number = self.twilio_client.messaging.v1.services(
                messaging_service_sid
            ).phone_numbers.create(phone_number_sid=phone_number_sid)

            logger.info(
                "Successfully added phone number to messaging service",
                extra={
                    "phone_number": phone_number,
                    "messaging_service_sid": messaging_service_sid,
                    "messaging_phone_number_sid": messaging_phone_number.sid,
                },
            )

        except Exception as e:
            # Log the error but don't raise to avoid interrupting the main workflow
            logger.warning(
                f"Failed to add phone number {phone_number} to messaging service: {e}",
                extra={
                    "phone_number": phone_number,
                    "error": str(e),
                },
            )

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

    def _is_number_associated_with_project(self, phone_number: str, session) -> bool:
        """
        Check if a phone number is associated with any project.

        Args:
            phone_number: The phone number to check
            session: Database session for project lookups

        Returns:
            True if the number is associated with any project, False otherwise
        """
        try:
            project_repo = ProjectRepository(session, auto_commit=False)
            projects = project_repo.get_projects_by_phone_number(phone_number)
            return len(projects) > 0
        except Exception:
            # Fail silently - caller will handle validation failure appropriately
            return False

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

            # Find associated projects and accounts using repository
            project_repo = ProjectRepository(session, auto_commit=False)
            projects = project_repo.get_projects_by_phone_number(phone_number)

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

            # Determine voice provider from trunk_sid (already fetched)
            voice_provider = (
                "livekit" if getattr(twilio_number, "trunk_sid", None) else None
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
                "voice_provider": voice_provider,
            }
            phone_numbers_data.append(phone_number_data)

        return phone_numbers_data, has_more
