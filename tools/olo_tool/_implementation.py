import json
import time
import urllib.parse
from functools import cached_property
from typing import Any

from agno.tools.toolkit import Toolkit
from cryptography.fernet import Fernet
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.olo_tool._apis import (
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

# Note: connect_olo_order_hub will be deprecated in favor of the signed requests version
from tools.olo_tool._apis._utils import connect_olo_order_hub
from tools.olo_tool._apis._utils import (
    connect_olo_order_hub_signed_requests as connect_olo_order_hub_signed,
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
    ValidatedBasketTotals,
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

HARD_CODED_PAYMENT_IFRAME_SECRET = "xK8dP2m_QrZ7vN4wL9cF3bJ6hT5yU1gS0aE8iO-pMxA="


class OloTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        index_name: str,
        tool_metadata: ToolMetadata,
        client_credentials: str | None = None,
        use_signed_auth: bool = True,
        hosted_payment_iframe_endpoint: str = "http://localhost:3000/checkout/olo",
        enable_hosted_checkout: bool = False,
        payment_iframe_token_ttl_seconds: int = 15 * 60,
        backdoor_tool_prompt: dict | None = None,
        brand_access_id: str | None = None,
    ):
        super().__init__(name="olo_tool")

        self.store_id = store_id
        self.namespace = namespace
        self.index_name = index_name
        self.tool_metadata = tool_metadata
        self._cached_store_info: str | None = None
        self.client_credentials = client_credentials
        self.use_signed_auth = use_signed_auth
        self.hosted_payment_iframe_endpoint = hosted_payment_iframe_endpoint
        self.enable_hosted_checkout = enable_hosted_checkout
        self.payment_iframe_token_ttl_seconds = payment_iframe_token_ttl_seconds
        self.backdoor_tool_prompt = backdoor_tool_prompt or {}
        self._configured_brand_access_id = brand_access_id
        # Set it as constant for now. If they want to make it dynamic later we can update it:
        ## Generate session-specific forwarded IP using session_id as seed
        ## This ensures the same session always gets the same IP, even if tool is reinitialized
        self.forwarded_ip = "10.23.17.89"
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
                logger.debug(
                    "[OLO] OloTool._olo_token Using signed authentication",
                    extra={"credential_secret": self.client_credentials},
                )
                return OloSignedToken(
                    client_id=credentials["client_id"],
                    client_secret=credentials["client_secret"],
                )

            api_key = get_client_secret_with_fallback("OLO_MOOYAH_API_KEY").strip()
            if not api_key:
                raise ValueError(
                    "OLO_MOOYAH_API_KEY is not configured; unable to authenticate Olo API calls"
                )
            logger.debug("[OLO] OloTool._olo_token Using API key authentication")
            return OloAccessToken(access_token=api_key, token_type="OloKey")

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
                forwarded_ip=self.forwarded_ip,
            )
        else:
            return connect_olo_order_hub(
                http_method=http_method,
                bearer_token=token,
                api_function=api_function,
                query_params=query_params,
                extra_headers=extra_headers,
                payload=payload,
                forwarded_ip=self.forwarded_ip,
            )

    @cached_property
    def _brand_access_id(self) -> str:
        if not self._configured_brand_access_id:
            raise ValueError(
                "brand_access_id must be provided in the tool configuration"
            )
        return self._configured_brand_access_id

    @cached_property
    def _payment_iframe_fernet(self) -> Fernet:
        try:
            return Fernet(HARD_CODED_PAYMENT_IFRAME_SECRET.encode("utf-8"))
        except ValueError as exc:
            raise ValueError(
                "HARD_CODED_PAYMENT_IFRAME_SECRET must be a URL-safe base64-encoded 32-byte key"
            ) from exc

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
                int(self.store_id), self._olo_token, forwarded_ip=self.forwarded_ip
            ).model_dump()

            # Remove isavailable and iscurrentlyopen from the store info since they should be most up to date and not stored in the cache
            store_dict.pop("isavailable", None)
            store_dict.pop("iscurrentlyopen", None)
            store_info = json.dumps(store_dict)

            # Cache store info for future use
            self._cached_store_info = store_info
            return store_info

        except Exception as e:
            logger.error(f"[OLO] OloTool.store_info Error getting store info: {e}")
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

            status = get_online_ordering_status(
                int(self.store_id), self._olo_token, forwarded_ip=self.forwarded_ip
            )

            if isinstance(status, int):
                return f"The restaurant is accepting online orders. The estimated ASAP order lead time is {status} minutes."
            else:
                return status

        except Exception as e:
            logger.error(
                f"[OLO] OloTool.check_online_ordering_status Error checking online ordering status: {e}"
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
                int(self.store_id),
                address_obj,
                self._olo_token,
                forwarded_ip=self.forwarded_ip,
            )

            if validated_address.candeliver:
                return "The address is valid."
            else:
                return f"The address is invalid. {validated_address.message}"
        except Exception as e:
            logger.error(
                f"[OLO] OloTool.validate_address_tool Error validating address: {e}"
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
        Completes checkout once the guest has confirmed their order.

        When hosted checkout is enabled this will return a secure payment link that
        directs the guest to our Olo payment iframe. Otherwise the order is submitted
        as a traditional pay-in-store transaction.
        """
        if self.enable_hosted_checkout:
            return self._checkout_order_with_payment_iframe()
        return self._checkout_order_wout_payment_iframe()

    def _checkout_order_wout_payment_iframe(self) -> str:
        try:
            logger.debug(
                "[OLO] OloTool._checkout_order_wout_payment_iframe Starting checkout",
                extra={"store_id": self.store_id},
            )
            # Create a basket
            basket = create_basket(
                int(self.store_id), self._olo_token, forwarded_ip=self.forwarded_ip
            )
            logger.debug(
                "[OLO] OloTool._checkout_order_wout_payment_iframe Basket created",
                extra={"basket_id": getattr(basket, "id", None)},
            )

            # Get the billing schemes info
            billing_schemes_info = get_billing_schemes_info(
                basket.id, self._olo_token, forwarded_ip=self.forwarded_ip
            )
            logger.debug(
                "[OLO] OloTool._checkout_order_wout_payment_iframe Retrieved billing schemes",
                extra={"scheme": billing_schemes_info},
            )

            # Construct the order
            order_input = self._construct_order(billing_schemes_info)
            # If the order is a string, return it
            if isinstance(order_input, str):
                logger.debug(
                    "[OLO] OloTool._checkout_order_wout_payment_iframe Order construction error",
                    extra={"message": order_input},
                )
                return order_input  # Failed to construct order

            logger.debug(
                "[OLO] OloTool._checkout_order_wout_payment_iframe Order constructed",
                extra={
                    "products": len(order_input.products),
                    "handoff_mode": order_input.handoffmode.value,
                },
            )

            # Add items to the basket
            add_items_to_basket(
                basket.id,
                olo_product_input=order_input,
                olo_token=self._olo_token,
                forwarded_ip=self.forwarded_ip,
            )
            logger.debug(
                "[OLO] OloTool._checkout_order_wout_payment_iframe Items added to basket",
                extra={"basket_id": basket.id},
            )

            # Set the handoff mode to pickup
            set_basket_handoff_mode(
                basket.id,
                handoff_mode=order_input.handoffmode,
                olo_token=self._olo_token,
                forwarded_ip=self.forwarded_ip,
            )
            logger.debug(
                "[OLO] OloTool._checkout_order_wout_payment_iframe Handoff mode set",
                extra={"handoff_mode": order_input.handoffmode.value},
            )

            # Validate the basket before submitting
            validate_basket(
                basket.id, olo_token=self._olo_token, forwarded_ip=self.forwarded_ip
            )
            logger.debug(
                "[OLO] OloTool._checkout_order_wout_payment_iframe Basket validated",
                extra={"basket_id": basket.id},
            )

            #######
            # Pay with credit card
            #######
            # Request a CCSF token
            # This is the test case for paying with credit card
            credit_token = request_ccsf_token(
                basket_id=basket.id,
                olo_token=self._olo_token,
                forwarded_ip=self.forwarded_ip,
            ).accesstoken

            # Create order submission body
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

            ####### DO NOT REMOVE THIS COMMENTED OUT CODE #######
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
                forwarded_ip=self.forwarded_ip,
            )
            logger.debug(
                "[OLO] OloTool._checkout_order_wout_payment_iframe Order submitted",
                extra={
                    "order_id": getattr(order_response, "id", None),
                    "total": getattr(order_response, "total", None),
                },
            )

            return (
                f"Order submitted successfully. The order ID is {order_response.id}. "
                f"Total cost: {order_response.total}. "
                f"Order contents: {order_response.products}. "
                f"Your OLO ID is {order_response.oloid}. When reaching out to Olo about an order, please provide this id."
            )

        except Exception as e:
            logger.error(
                f"[OLO] OloTool._checkout_order_wout_payment_iframe Error checking out order: {e}"
            )
            return "Failed to check out the order, please try again."

    def _checkout_order_with_payment_iframe(self) -> str:
        try:
            logger.debug(
                "[OLO] OloTool._checkout_order_with_payment_iframe Starting hosted checkout",
                extra={
                    "store_id": self.store_id,
                    "session_id": getattr(self.tool_metadata, "session_id", None),
                },
            )
            basket = create_basket(
                int(self.store_id), self._olo_token, forwarded_ip=self.forwarded_ip
            )
            billing_schemes_info = get_billing_schemes_info(
                basket.id, self._olo_token, forwarded_ip=self.forwarded_ip
            )
            logger.debug(
                "[OLO] OloTool._checkout_order_with_payment_iframe Basket created",
                extra={"basket_id": getattr(basket, "id", None)},
            )
            order_input = self._construct_order(billing_schemes_info)
            if isinstance(order_input, str):
                return order_input
            logger.debug(
                "[OLO] OloTool._checkout_order_with_payment_iframe Order constructed",
                extra={
                    "products": len(order_input.products),
                    "handoff_mode": order_input.handoffmode.value,
                    "has_customer_email": bool(order_input.emailaddress),
                },
            )

            add_items_to_basket(
                basket.id,
                olo_product_input=order_input,
                olo_token=self._olo_token,
                forwarded_ip=self.forwarded_ip,
            )
            set_basket_handoff_mode(
                basket.id,
                handoff_mode=order_input.handoffmode,
                olo_token=self._olo_token,
                forwarded_ip=self.forwarded_ip,
            )
            basket_totals = validate_basket(
                basket.id, olo_token=self._olo_token, forwarded_ip=self.forwarded_ip
            )
            logger.debug(
                "[OLO] OloTool._checkout_order_with_payment_iframe Basket validated",
                extra={
                    "subtotal": basket_totals.subtotal,
                    "tax": basket_totals.tax,
                    "total": basket_totals.total,
                },
            )

            ccsf_access_token = request_ccsf_token(
                basket_id=basket.id,
                olo_token=self._olo_token,
                forwarded_ip=self.forwarded_ip,
            ).accesstoken
            logger.debug(
                "[OLO] OloTool._checkout_order_with_payment_iframe CCSF token retrieved",
                extra={
                    "basket_id": basket.id,
                    "token_preview": f"{ccsf_access_token[:6]}...{ccsf_access_token[-4:]}",
                },
            )

            payment_payload = self._build_hosted_payment_payload(
                basket_id=basket.id,
                order_input=order_input,
                basket_totals=basket_totals,
                ccsf_access_token=ccsf_access_token,
            )
            logger.debug(
                "[OLO] OloTool._checkout_order_with_payment_iframe Payment payload built",
                extra={
                    "expires_at": payment_payload.get("expiresAt"),
                    "handoff_mode": payment_payload.get("handoffMode"),
                },
            )

            payment_link = self._generate_payment_link(payment_payload)
            confirmation_message = self._format_checkout_confirmation(basket_totals)
            sanitized_link = self._sanitize_payment_link(payment_link)
            logger.debug(
                "[OLO] OloTool._checkout_order_with_payment_iframe Payment link generated",
                extra={"payment_link": sanitized_link},
            )

            return (
                confirmation_message
                + f"\n\nThe following is the payment link, ask the user to use the link to checkout: [payment link]({payment_link})\n\nYou MUST INCLUDE THE COMPLETE URL in your response, formatted as a Markdown link. YOU MUST NOT OMIT ANY PART OF THE URL."
            )

        except Exception as e:
            logger.error(
                f"[OLO] OloTool._checkout_order_with_payment_iframe Error starting checkout: {e}"
            )
            return "Failed to start the checkout process. Please try again."

    def _build_hosted_payment_payload(
        self,
        *,
        basket_id: str,
        order_input: OloProductInput,
        basket_totals: ValidatedBasketTotals,
        ccsf_access_token: str,
    ) -> dict[str, Any]:
        order_submission: dict[str, Any] = {
            "userType": UserType.guest.value,
            "firstName": order_input.firstname,
            "lastName": order_input.lastname,
            "emailAddress": order_input.emailaddress,
            "contactNumber": order_input.contactnumber,
            "billingAccounts": [
                {
                    "amount": round(float(basket_totals.total), 2),
                    "billingMethod": BillingMethod.creditcard.value,
                    "tipPortion": 0,
                }
            ],
        }
        if order_input.billingschemeid:
            order_submission["billingSchemeId"] = order_input.billingschemeid

        session_id = getattr(self.tool_metadata, "session_id", None)
        if session_id is not None:
            session_id = str(session_id)

        payload: dict[str, Any] = {
            "storeId": self.store_id,
            "basketId": basket_id,
            "brandAccessId": self._brand_access_id,
            "accessToken": ccsf_access_token,
            "orderSubmission": order_submission,
            "basketTotals": {
                "subtotal": round(float(basket_totals.subtotal), 2),
                "tax": round(float(basket_totals.tax), 2),
                "total": round(float(basket_totals.total), 2),
                "fees": round(float(basket_totals.totalfees), 2),
                "customerHandoffCharge": round(
                    float(basket_totals.customerhandoffcharge), 2
                ),
                "readyTime": basket_totals.readytime,
            },
            "orderItems": [
                product.model_dump(exclude_none=True)
                for product in order_input.products
            ],
            "handoffMode": order_input.handoffmode.value,
            "customer": {
                "firstName": order_input.firstname,
                "lastName": order_input.lastname,
                "emailAddress": order_input.emailaddress,
                "contactNumber": order_input.contactnumber,
            },
            "sessionId": session_id,
            "expiresAt": int(time.time()) + self.payment_iframe_token_ttl_seconds,
        }
        logger.debug(
            "[OLO] OloTool._build_hosted_payment_payload Payload composed",
            extra={
                "store_id": payload["storeId"],
                "basket_id": payload["basketId"],
                "order_items": len(payload["orderItems"]),
                "expires_at": payload["expiresAt"],
            },
        )
        return payload

    def _generate_payment_link(self, payload: dict[str, Any]) -> str:
        token_bytes = self._payment_iframe_fernet.encrypt(
            json.dumps(payload).encode("utf-8")
        )
        token = urllib.parse.quote(token_bytes.decode("utf-8"))
        logger.debug(
            "[OLO] OloTool._generate_payment_link Token generated",
            extra={
                "token_preview": f"{token[:12]}..." if token else "",
                "hosted_endpoint": self.hosted_payment_iframe_endpoint,
            },
        )
        return f"{self.hosted_payment_iframe_endpoint}?t={token}"

    def _sanitize_payment_link(self, payment_link: str) -> str:
        try:
            parsed = urllib.parse.urlparse(payment_link)
            query_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            if "t" in query_params:
                query_params["t"] = ["[REDACTED]"]
            sanitized_query = urllib.parse.urlencode(query_params, doseq=True)
            return urllib.parse.urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    sanitized_query,
                    parsed.fragment,
                )
            )
        except Exception:
            return self.hosted_payment_iframe_endpoint

    @staticmethod
    def _format_checkout_confirmation(basket_totals: ValidatedBasketTotals) -> str:
        total = round(float(basket_totals.total), 2)
        ready_time = basket_totals.readytime
        ready_time_text = (
            f" It will be ready around {ready_time}." if ready_time else ""
        )
        return (
            f"I've prepared your order. The total is ${total:.2f}.{ready_time_text} "
            "Please use the secure payment link below to complete checkout."
        )
