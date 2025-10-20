import json
from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.olo_tool._apis import (  # TODO: Add request_ccsf_token
    add_items_to_basket,
    create_basket,
    get_billing_schemes_info,
    get_online_ordering_status,
    get_store_info,
    request_ccsf_token,
    set_basket_handoff_mode,
    submit_order,
    validate_address,
    validate_basket,
)
from tools.olo_tool._apis._utils import (
    connect_olo_order_hub,
    connect_olo_order_hub_signed,
)
from tools.olo_tool._prompt_constants import (
    EXTRACTOR_SYSTEM_PROMPT,
    EXTRACTOR_USER_PROMPT,
    RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
)
from tools.olo_tool.classes import (
    Address,
    BillingMethod,
    BillingScheme,
    OloAccessToken,
    OloOrderSubmissionBody,
    OloProductInput,
    OloSignedToken,
    UserType,
)
from tools.utils.ordering._query_engine import create_query_engine
from tools.utils.ordering._utils import (
    construct_order,
    get_chat_history,
    get_relevant_docs,
)
from tools.utils.ordering.classes import HttpMethod, SubQueries
from utils.log import logger
from utils.secret import get_client_secret_with_fallback


class OloTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        index_name: str,
        tool_metadata: ToolMetadata,
        client_credentials: str | None = None,
        use_signed_auth: bool = False,
        backdoor_tool_prompt: dict | None = None,
    ):
        super().__init__(name="olo_tool")

        self.store_id = store_id
        self.namespace = namespace
        self.index_name = index_name
        self.tool_metadata = tool_metadata
        self._cached_store_info: str | None = None
        self.client_credentials = client_credentials
        self.use_signed_auth = use_signed_auth
        self.backdoor_tool_prompt = backdoor_tool_prompt or {}
        # Register tools
        self.register(self.get_store_info_tool)
        self.register(self.check_online_ordering_status)
        self.register(self.validate_address_tool)
        self.register(self.checkout_order)

        # Retrieval tools
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)
        self.query_engine = create_query_engine(
            namespace=self.namespace, index_name=self.index_name, top_k=3
        )

    @cached_property
    def _olo_token(self) -> OloAccessToken | OloSignedToken:
        """
        Retrieves and caches the Olo API access token or signed credentials.

        Returns:
            OloAccessToken or OloSignedToken: Authentication object for Olo API calls.

        Raises:
            ValueError: If the required credentials are not set.
        """
        with LLMObs.task(name="get_olo_token"):
            if self.use_signed_auth:
                if not self.client_credentials:
                    raise ValueError(
                        "client_credentials is required when use_signed_auth=True"
                    )
                credentials = self._get_olo_credentials(self.client_credentials)
                return OloSignedToken(
                    client_id=credentials["client_id"],
                    client_secret=credentials["client_secret"],
                )
            else:
                api_key = get_client_secret_with_fallback("OLO_MOOYAH_API_KEY")
                return OloAccessToken(
                    access_token=api_key,
                    token_type="OloKey",
                )

    def _get_olo_credentials(self, client_credentials: str) -> dict[str, str]:
        """
        Retrieves the Olo credentials from the secrets manager.

        Args:
            client_credentials: The client credentials to use. We will use this to get the Olo credentials from the secrets manager.

        Returns:
            dict: {"client_id": "...", "client_secret": "..."}
        """
        raw = get_client_secret_with_fallback(client_credentials)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Secret '{client_credentials}' is not valid JSON: {e.msg}"
            ) from e

        for key in ("client_id", "client_secret"):
            val = data.get(key)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(
                    f"Secret '{client_credentials}' is missing required field '{key}'"
                )

        return {
            "client_id": data["client_id"].strip(),
            "client_secret": data["client_secret"].strip(),
        }

    def _connect_olo_api(
        self,
        http_method,
        api_function,
        query_params=None,
        extra_headers=None,
        payload=None,
    ):
        """
        Helper method to connect to Olo API using the appropriate authentication method.

        Args:
            http_method: The HTTP method to use
            api_function: The API endpoint to call
            query_params: Optional query parameters
            extra_headers: Optional additional headers
            payload: Optional request payload

        Returns:
            GenericHubResponse: The API response
        """
        # Convert string method to HttpMethod enum if needed
        if isinstance(http_method, str):
            http_method = HttpMethod(http_method.upper())

        token = self._olo_token

        if isinstance(token, OloSignedToken):
            return connect_olo_order_hub_signed(
                http_method=http_method,
                signed_token=token,
                api_function=api_function,
                query_params=query_params,
                extra_headers=extra_headers,
                payload=payload,
            )
        else:
            return connect_olo_order_hub(
                http_method=http_method,
                bearer_token=token,
                api_function=api_function,
                query_params=query_params,
                extra_headers=extra_headers,
                payload=payload,
            )

    @tool
    def get_store_info_tool(self) -> str:
        """
        Retrieves detailed configuration information for a specific restaurant.

        Args:
            None

        Returns:
            str: A JSON-formatted string containing OloStore object
        """

        try:
            # If store info is already cached return it
            if self._cached_store_info:
                return self._cached_store_info

            if not self._olo_token:
                return (
                    "Failed to authenticate Olo ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            # Get store info from Olo
            store_dict = get_store_info(
                int(self.store_id), self._olo_token
            ).model_dump()

            # Remove isavailable and iscurrentlyopen from the store info since they should be most up to date and not stored in the cache
            store_dict.pop("isavailable", None)
            store_dict.pop("iscurrentlyopen", None)
            store_info = json.dumps(store_dict)

            # Cache store info for future use
            self._cached_store_info = store_info
            return store_info

        except Exception as e:
            logger.error(f"[OloTool.store_info] Error getting store info: {e}")
            return "Failed to get the store information, please try again."

    @tool
    def check_online_ordering_status(self) -> str:
        """
        Retrieves the current online ordering availability status of a specified restaurant.

        Args:
            None

        Returns:
            str: A string containing:
            - The restaurant's online ordering availability status
            - The estimated lead time if orders are being accepted
        """
        try:
            if not self._olo_token:
                return (
                    "Failed to authenticate Olo ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            status = get_online_ordering_status(int(self.store_id), self._olo_token)

            if isinstance(status, int):
                return f"The restaurant is accepting online orders. The estimated ASAP order lead time is {status} minutes."
            else:
                return status

        except Exception as e:
            logger.error(
                f"[OloTool.check_online_ordering_status] Error checking online ordering status: {e}"
            )
            return "Failed to check the online ordering status, please try again."

    @tool
    def validate_address_tool(
        self, street_address: str, city: str, zipcode: str
    ) -> str:
        """
        Validates an address for delivery to determine if the restaurant can deliver to the specified location.

        Args:
            street_address: The street address of the location to validate.
            city: The city of the location to validate.
            zipcode: The zipcode of the location to validate.

        Returns:
            str: A message indicating whether the address is valid or not
        """
        try:
            if not self._olo_token:
                return (
                    "Failed to authenticate Olo ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            # Remove any extra spaces in zipcode
            zipcode = zipcode.replace(" ", "")

            # Create address object
            address_obj = Address(
                streetaddress=street_address,
                city=city,
                zipcode=zipcode,
            )

            # Validate address
            validated_address = validate_address(
                int(self.store_id), address_obj, self._olo_token
            )

            if validated_address.candeliver:
                return "The address is valid."
            else:
                return f"The address is invalid. {validated_address.message}"
        except Exception as e:
            logger.error(
                f"[OloTool.validate_address_tool] Error validating address: {e}"
            )
            return "Failed to validate the address, please try again."

    def _construct_order(
        self,
        billing_schemes_info: list[BillingScheme],
    ) -> OloProductInput | str:
        chat_history = get_chat_history(self.query_messages_tool)
        context = get_relevant_docs(
            self.query_engine,
            chat_history,
            self.backdoor_tool_prompt.get(
                "order_item_prompt", RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT
            ),
            response_format=SubQueries,
        )

        # Add the billing schemes info to the context
        context += f"\n\nThe billing schemes info is: {billing_schemes_info}. Choose the billing scheme id that is most appropriate for the order.\n"

        # Get prompt overrides or defaults
        system_prompt = self.backdoor_tool_prompt.get(
            "system_prompt", EXTRACTOR_SYSTEM_PROMPT
        )
        user_prompt_template = self.backdoor_tool_prompt.get(
            "user_prompt", EXTRACTOR_USER_PROMPT
        )

        return construct_order(
            system_prompt=system_prompt,
            user_prompt=user_prompt_template.format(
                context=context, chat_history=chat_history
            ),
            response_format=OloProductInput,
            openai=True,
        )

    @tool
    def checkout_order(self) -> str:
        """
        Validates an order for checkout by extracting structured ordering data from chat
        history. This function absolutely must be invoked when all the required information is collected and the user asks to checkout,
        pay, place the order, etc.

        Args:
            None

        Returns:
            str: Order checkout confirmation details
        """
        # We need to first create a basket, then add items to the basket, then set the handoff mode to pickup. For credit card payment, we need to request a CCSF token, then submit the order; for pay in store, we need to submit the order.
        # We focus on pay in store for now.
        try:
            # Create a basket
            basket = create_basket(int(self.store_id), self._olo_token)

            # Get the billing schemes info
            billing_schemes_info = get_billing_schemes_info(basket.id, self._olo_token)

            # Construct the order
            order_input = self._construct_order(billing_schemes_info)
            # If the order is a string, return it
            if isinstance(order_input, str):
                return order_input  # Failed to construct order

            # Add items to the basket
            add_items_to_basket(
                basket.id, olo_product_input=order_input, olo_token=self._olo_token
            )

            # Set the handoff mode to pickup
            set_basket_handoff_mode(
                basket.id,
                handoff_mode=order_input.handoffmode,
                olo_token=self._olo_token,
            )

            # Validate the basket
            validate_basket(basket.id, olo_token=self._olo_token)

            #######
            # Pay with credit card
            #######
            # Request a CCSF token
            # This is the test case for paying with credit card
            credit_token = request_ccsf_token(
                basket_id=basket.id,
                olo_token=self._olo_token,
            ).accesstoken

            # # Create order submission body
            order_submission = OloOrderSubmissionBody(
                billingmethod=BillingMethod.creditcardtoken,
                usertype=UserType.guest,
                token=credit_token,
                expiryyear=2025,
                expirymonth=12,
                cardtype="Visa",
                cardlastfour="1234",
                streetaddress="123 Main St",
                city="Anytown",
                state="CA",
                zip="12345",
                country="US",
                saveonfile="false",
                firstname=order_input.firstname,
                lastname=order_input.lastname,
                emailaddress=order_input.emailaddress,
                contactnumber=order_input.contactnumber,
            )

            #######
            # Pay in store
            #######
            # Submit the order
            # order_submission = OloOrderSubmissionBody(
            #     billingmethod=BillingMethod.payinstore,
            #     usertype=UserType.guest,
            #     billingschemeid=order_input.billingschemeid,
            #     saveonfile="false",
            #     firstname=order_input.firstname,
            #     lastname=order_input.lastname,
            #     emailaddress=order_input.emailaddress,
            #     contactnumber=order_input.contactnumber,
            # )
            order_response = submit_order(
                basket_id=basket.id,
                olo_token=self._olo_token,
                olo_order_submission_body=order_submission,
            )

            return f"Order submitted successfully. The order ID is {order_response.id}. Total cost: {order_response.total}. Order contents: {order_response.products}. Your OLO ID is {order_response.oloid}. When reaching out to Olo about an order, please provide this id."

        except Exception as e:
            logger.error(f"[OloTool.checkout_order] Error checking out order: {e}")
            return "Failed to check out the order, please try again."
