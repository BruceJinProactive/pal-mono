from typing import List, Optional, Tuple

from twilio.rest import Client
from twilio.rest.api.v2010.account.incoming_phone_number import (
    IncomingPhoneNumberInstance,
)
from vapi import Vapi
from vapi.phone_numbers.types.phone_numbers_create_response import (
    PhoneNumbersCreateResponse,
)
from vapi.types.assistant import Assistant
from vapi.types.create_twilio_phone_number_dto import CreateTwilioPhoneNumberDto
from vapi.types.custom_llm_model import CustomLlmModel
from vapi.types.server import Server

import db
from utils import secret

from ._utils import (
    AssistantConfig,
    NumberDetails,
    get_server_url,
    get_twilio_friendly_name,
)


class NumberService:
    """
    Service for managing phone numbers and Vapi assistants.

    This service handles:
    1. Purchasing phone numbers from Twilio (both local and toll-free)
    2. Creating Vapi assistants with custom LLM models
    3. Importing numbers to Vapi
    4. Assigning numbers to projects

    The service requires the following secrets to be configured:
    - TWILIO_ACCOUNT_SID: Your Twilio account SID
    - TWILIO_AUTH_TOKEN: Your Twilio auth token
    - VAPI_API_KEY: Your Vapi API key

    Example:
        ```python
        # Initialize the service
        # Initialize the service
        number_service = NumberService()

        # Set up a number with an assistant
        assistant_config = AssistantConfig(
            merchant_name="My Business",
            model_url="https://lat-api.palona.ai/v1/",
            model_name="palona-voice-default",
            server_url="https://example.com/webhook"  # Optional: if provided, assistant will use settings from this URL
        )
        number_details, assistant, vapi_response = number_service.setup_number(
            country_code="US",
            toll_free=True,
            assistant_config=assistant_config,
            project=project
        )
        ```

    Raises:
        RuntimeError: If any required secrets are missing or invalid
    """

    def __init__(self):
        """
        Initialize the number service.

        This method:
        1. Retrieves required secrets (Twilio and Vapi credentials)
        2. Validates that all secrets are present
        3. Initializes Twilio and Vapi clients

        Required secrets:
        - TWILIO_ACCOUNT_SID: Your Twilio account SID
        - TWILIO_AUTH_TOKEN: Your Twilio auth token
        - VAPI_API_KEY: Your Vapi API key

        Raises:
            RuntimeError: If any required secrets are missing or invalid
            KeyError: If any required secrets are not found
        """
        try:
            # Retrieve each secret via public API
            twilio_account_sid = secret.get_server_secret("TWILIO_ACCOUNT_SID")
            twilio_auth_token = secret.get_server_secret("TWILIO_AUTH_TOKEN")
            vapi_token = secret.get_server_secret("VAPI_API_KEY")

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

            self.twilio_client = Client(twilio_account_sid, twilio_auth_token)
            self.vapi_client = Vapi(token=vapi_token)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize NumberService: {e}") from e

    def purchase_number(self, country_code: str, friendly_name: str) -> NumberDetails:
        """
        Purchase a new local phone number through Twilio.

        This method:
        1. Searches for available local numbers in the specified country
        2. Purchases the first available number
        3. Returns the purchased number instance

        Args:
            country_code (str): The country code to search for numbers in.
                Common values:
                - "US" for United States
                - "CA" for Canada
                - "GB" for the United Kingdom
            friendly_name (str): The display name of the purchased phone number

        Returns:
            IncomingPhoneNumberInstance: The purchased phone number instance.
                Contains:
                - phone_number: The actual phone number
                - friendly_name: Current display name
                - sid: Twilio's unique identifier

        Raises:
            ValueError: If no numbers are available for the given country code

        Example:
            ```python
            number = number_service.purchase_number("CA")
            print(f"Purchased: {number.phone_number}")
            ```
        """
        available_numbers = self.twilio_client.available_phone_numbers(
            country_code
        ).local.list(limit=1)

        if not available_numbers:
            raise ValueError(
                f"No available phone numbers found for country code {country_code}"
            )

        number = available_numbers[0]
        twilio_number = self.twilio_client.incoming_phone_numbers.create(
            phone_number=number.phone_number,
            friendly_name=friendly_name,
        )
        if not twilio_number.phone_number:
            raise ValueError("Failed to get phone number from Twilio")

        return NumberDetails(
            number=twilio_number.phone_number,
            merchant_name="",
            project_name=None,
            country_code=country_code,
            toll_free=False,
        )

    def purchase_toll_free_number(
        self, country_code: str, friendly_name: str
    ) -> NumberDetails:
        """
        Purchase a new toll-free phone number through Twilio.

        This method:
        1. Searches for available toll-free numbers in the specified country
        2. Purchases the first available number
        3. Returns the number details

        Args:
            country_code (str): The country code to search for numbers in.
                Common values:
                - "US" for United States
                - "CA" for Canada
                - "GB" for the United Kingdom
            friendly_name (str): The display name of the purchased phone number

        Returns:
            NumberDetails: The purchased phone number details.
                Contains:
                - number: The actual phone number
                - merchant_name: Empty string (to be set later)
                - project_name: None (to be set later)
                - toll_free: True
                - country_code: The provided country code

        Raises:
            ValueError: If no toll-free numbers are available for the given country code
            ValueError: If Twilio fails to provide a phone number

        Example:
            ```python
            number_details = number_service.purchase_toll_free_number("US")
            print(f"Purchased toll-free: {number_details['number']}")
            ```
        """
        available_numbers = self.twilio_client.available_phone_numbers(
            country_code
        ).toll_free.list(limit=1)

        if not available_numbers:
            raise ValueError(
                f"No available toll-free phone numbers found for country code {country_code}"
            )

        number = available_numbers[0]
        twilio_number = self.twilio_client.incoming_phone_numbers.create(
            phone_number=number.phone_number,
            friendly_name=friendly_name,
        )
        if not twilio_number.phone_number:
            raise ValueError("Failed to get toll-free phone number from Twilio")

        number_details = NumberDetails(
            number=twilio_number.phone_number,
            merchant_name="",  # Required field
            project_name=None,  # Optional field
            country_code=country_code,
            toll_free=True,
        )
        return number_details

    def _create_assistant(self, config: AssistantConfig) -> Assistant:
        """
        Create a new Vapi assistant with a custom model.

        This method:
        1. Creates a new assistant in Vapi
        2. Configures it with the specified LLM model
        3. Returns the created assistant instance

        Args:
            config (AssistantConfig): Configuration for the assistant.
                Required fields:
                - merchant_name: Name of your business/assistant
                - model_url: URL of your LLM API (e.g., "https://lat-api.palona.ai/v1/")
                - model_name: Name of your model (e.g., "palona-voice-default")
                - server_url: URL for webhook callbacks (optional)

        Returns:
            Assistant: The created Vapi assistant instance.
                Contains:
                - id: Assistant's unique identifier
                - name: Assistant's name
                - model: Configured model details

        Example:
            ```python
            assistant_config = AssistantConfig(
                merchant_name="My Business",
                model_url="https://lat-api.palona.ai/v1/",
                model_name="palona-voice-default",
                server_url="https://example.com/webhook"  # Optional: if provided, assistant will use settings from this URL
            )
            assistant = number_service._create_assistant(assistant_config)
            ```
        """
        return self.vapi_client.assistants.create(
            name=config["merchant_name"],
            model=CustomLlmModel(url=config["model_url"], model=config["model_name"]),
        )

    def setup_number(
        self,
        country_code: str,
        toll_free: bool,
        project: db.Project,
        assistant_config: Optional[AssistantConfig] = None,
    ) -> Tuple[NumberDetails, Assistant | None, PhoneNumbersCreateResponse]:
        """
        Complete flow to set up a number with a Vapi assistant.

        This method handles the entire setup process:
        1. Creates a Vapi assistant with the specified model (if no server_url provided)
        2. Purchases a new phone number (local or toll-free)
        3. Imports the number to Vapi
        4. Assigns the number to the specified project

        Args:
            country_code (str): The country code to search for numbers in
            toll_free (bool): Whether to purchase a toll-free number
            assistant_config (AssistantConfig): Configuration for the assistant
            project (db.Project): The project to assign the number to

        Returns:
            Tuple containing:
            - NumberDetails: The phone number details
            - Assistant: The created Vapi assistant (None if using existing server)
            - PhoneNumbersCreateResponse: Vapi's response after importing the number

        Example:
            ```python
            number_details, assistant, vapi_response = number_service.setup_number(
                country_code="US",
                toll_free=True,
                project=project
            )
            ```
        """
        # use the server_url to get settings from the server, if not provided, create a new assistant
        if assistant_config:
            if assistant_config["server_url"]:
                assistant_id = None
                server_url = assistant_config["server_url"]
                assistant = None
            else:
                # Create the assistant
                assistant = self._create_assistant(assistant_config)
                assistant_id = assistant.id
                server_url = None
        else:
            assistant_id = None
            server_url = get_server_url()
            assistant = None

        # Purchase number
        friendly_name = get_twilio_friendly_name(project.name)
        if toll_free:
            number_details = self.purchase_toll_free_number(country_code, friendly_name)
        else:
            number_details = self.purchase_number(country_code, friendly_name)

        if not number_details or not number_details["number"]:
            raise ValueError("Failed to get phone number from Twilio")
        phone_number = number_details["number"]

        # Import number to Vapi
        vapi_response = self.vapi_client.phone_numbers.create(
            request=CreateTwilioPhoneNumberDto(
                number=phone_number,
                twilio_account_sid=self.twilio_client.username,  # type: ignore
                twilio_auth_token=self.twilio_client.password,
                name=(
                    assistant_config["merchant_name"]
                    if assistant_config
                    else project.name
                ),
                assistant_id=assistant_id,
                server=Server(url=server_url),
            ),
        )

        # Assign to project if needed
        number_details = NumberDetails(
            number=phone_number,
            merchant_name=(
                assistant_config["merchant_name"] if assistant_config else project.name
            ),
            project_name=project.name,
            toll_free=toll_free,
            country_code=country_code,
        )

        return number_details, assistant, vapi_response

    def get_purchased_numbers(
        self, limit: int = 20
    ) -> List[IncomingPhoneNumberInstance]:
        """
        Get a list of all purchased phone numbers.

        This method:
        1. Retrieves all numbers from your Twilio account
        2. Returns them as a list of number instances

        Args:
            limit (int): Maximum number of numbers to return.
                Default: 20

        Returns:
            List[IncomingPhoneNumberInstance]: List of purchased phone numbers.
                Each number contains:
                - phone_number: The actual number
                - friendly_name: Current display name
                - sid: Twilio's unique identifier

        Example:
            ```python
            numbers = number_service.get_purchased_numbers(limit=50)
            for number in numbers:
                print(f"{number.friendly_name}: {number.phone_number}")
            ```
        """
        return self.twilio_client.incoming_phone_numbers.list(limit=limit)
