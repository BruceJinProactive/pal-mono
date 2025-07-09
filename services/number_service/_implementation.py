import os
from typing import List, Optional

from twilio.rest import Client
from twilio.rest.api.v2010.account.incoming_phone_number import (
    IncomingPhoneNumberInstance,
)
from vapi import Vapi
from vapi.types.create_twilio_phone_number_dto import (
    CreateTwilioPhoneNumberDto,
)
from vapi.types.custom_llm_model import CustomLlmModel
from vapi.types.server import Server

from utils.log import logger

from ..service_utils import get_server_url
from ._utils import (
    AssistantConfig,
    NumberResponse,
)


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

    def purchase_number(self, country_code: str, merchant_name: str) -> NumberResponse:
        """Purchase a new local phone number from Twilio.

        Args:
            country_code: Two-letter country code (e.g., 'US')
            merchant_name: Business name to associate with the number

        Returns:
            NumberResponse containing the purchased number details

        Raises:
            ValueError: If no numbers are available or purchase fails
        """
        available_numbers = self.twilio_client.available_phone_numbers(
            country_code
        ).local.list(limit=1)

        if not available_numbers:
            raise ValueError(
                f"No available phone numbers found for country code {country_code}"
            )

        number = available_numbers[0]
        try:
            twilio_number = self.twilio_client.incoming_phone_numbers.create(
                phone_number=number.phone_number,
                friendly_name=self._get_friendly_name(merchant_name),
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
        self, country_code: str, merchant_name: str
    ) -> NumberResponse:
        """Purchase a new toll-free phone number from Twilio.

        Args:
            country_code: Two-letter country code (e.g., 'US')
            merchant_name: Business name to associate with the number

        Returns:
            NumberResponse containing the purchased toll-free number details

        Raises:
            ValueError: If no toll-free numbers are available or purchase fails
        """
        available_numbers = self.twilio_client.available_phone_numbers(
            country_code
        ).toll_free.list(limit=1)

        if not available_numbers:
            raise ValueError(
                f"No available toll-free phone numbers found for country code {country_code}"
            )

        number = available_numbers[0]
        try:
            twilio_number = self.twilio_client.incoming_phone_numbers.create(
                phone_number=number.phone_number,
                friendly_name=self._get_friendly_name(merchant_name),
            )
            if not twilio_number.phone_number:
                raise ValueError("Failed to get toll-free phone number from Twilio")
        except Exception as e:
            raise ValueError(f"Failed to purchase toll-free phone number: {e}") from e

        return NumberResponse(
            number=twilio_number.phone_number,
            merchant_name=twilio_number.friendly_name or "",
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
    ) -> NumberResponse:
        """Set up a phone number with optional Vapi assistant integration.

        This method handles the complete setup process:
        1. Creates a Vapi assistant if configuration is provided
        2. Purchases a phone number (local or toll-free)
        3. Integrates the number with Vapi
        4. Handles cleanup if any step fails

        Args:
            country_code: Two-letter country code (e.g., 'US')
            toll_free: Whether to purchase a toll-free number
            merchant_name: Business name to associate with the number
            assistant_config: Optional configuration for Vapi assistant

        Returns:
            NumberResponse containing the set up number details

        Raises:
            ValueError: If number setup or integration fails
        """
        # use the server_url to get settings from the server, if not provided, create a new assistant

        if assistant_config:
            if assistant_config["server_url"]:
                assistant_id = None
                server_url = assistant_config["server_url"]
            else:
                # Create the assistant
                assistant_id = self._create_assistant_and_get_id(assistant_config)
                server_url = None
        else:
            assistant_id = None
            server_url = f"{get_server_url()}/v1/integrations/vapi/"

        merchant_name = (
            assistant_config["merchant_name"] if assistant_config else merchant_name
        )
        # Purchase number
        if toll_free:
            number_response = self.purchase_toll_free_number(
                country_code, merchant_name
            )
        else:
            number_response = self.purchase_number(country_code, merchant_name)

        if not number_response or not number_response.number:
            raise ValueError("Failed to get phone number from Twilio")
        phone_number = number_response.number

        # Import number to Vapi
        try:
            self.vapi_client.phone_numbers.create(
                request=CreateTwilioPhoneNumberDto(
                    number=phone_number,
                    twilio_account_sid=self.twilio_client.username,  # type: ignore
                    twilio_auth_token=self.twilio_client.password,
                    name=self._get_friendly_name(merchant_name),
                    assistant_id=assistant_id,
                    server=Server(url=server_url),
                ),
            )
        except Exception as e:
            self._release_number_from_twilio(
                phone_number
            )  # release the purchased number if the vapi call fails
            raise ValueError(f"Failed to import number to Vapi: {e}") from e

        return number_response

    def get_purchased_numbers(
        self, limit: int = 20
    ) -> List[IncomingPhoneNumberInstance]:
        """Retrieve a list of all purchased phone numbers from Twilio.

        Args:
            limit: Maximum number of numbers to return (default: 20)

        Returns:
            List of Twilio IncomingPhoneNumberInstance objects containing:
            - phone_number: The actual number
            - friendly_name: Current display name
            - sid: Twilio's unique identifier
        """
        return self.twilio_client.incoming_phone_numbers.list(limit=limit)

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
        """Release a phone number from Twilio.

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
                    n.delete()
                    break
        except Exception as e:
            raise ValueError(f"Failed to release number from Twilio: {e}") from e

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

    def _get_friendly_name(self, business_name: str) -> str:
        stage = os.environ.get("RUNTIME_ENV") or "dev"
        if stage == "prd":
            return business_name
        else:
            return f"{stage}:{business_name}"
