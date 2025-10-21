import asyncio
import json
import re
import traceback
from datetime import datetime
from typing import List

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, task, tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from db.session import SyncSessionLocal
from db.tables.adora_orders import AdoraOrder as DBOrder
from db.tables.types import IntegrationProvider
from services.transaction_service import save_order
from tools.adora_tool.classes import (
    AdoraAccessToken,
    AdoraLatestOrderResponse,
    AdoraOrderCalculationResult,
    AdoraOrderType,
    DeliveryAddress,
    LoyaltyNextOrderCredit,
    LoyaltyOffer,
    LoyaltyReward,
    Order,
    SubQueries,
)
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

from . import _apis, _llm, _query_engine, _utils

ADORA_QA_STORE = "UQ5ZT"
ADORA_QA_STORE_2 = "LE5AR"
VIA_AGENT_SUFFIX = "(via PalonaAI)"


class AdoraTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        tool_metadata: ToolMetadata,
        loyalty_enabled: bool = False,
        coupons_enabled: bool = False,
        default_coupon_id: int | None = None,
        token_api_endpoint: str | None = None,
        general_api_endpoint: str | None = None,
        backdoor_tool_prompt: dict | None = None,
    ):
        super().__init__(name="adora_tool")

        # Log instance creation with built-in id
        instance_id = id(self)
        logger.debug(f"AdoraTool instance created: id={instance_id}")

        # Configs
        self.store_id = store_id
        self.namespace = namespace
        self.tool_metadata = tool_metadata
        self.discounts = []  # { coupon_id, coupon_code }
        self.default_coupon_id = default_coupon_id
        self.loyalty_enabled = loyalty_enabled
        self.coupons_enabled = coupons_enabled
        self.token_api_endpoint = token_api_endpoint
        self.general_api_endpoint = general_api_endpoint
        self.backdoor_tool_prompt = backdoor_tool_prompt or {}
        if self.store_id in [ADORA_QA_STORE, ADORA_QA_STORE_2]:  # QA store
            self.qa_store = True
        else:
            self.qa_store = False

        ### Cache adora token and store info ###
        self.cached_store_info: str | None = None

        self._adora_bearer_token: AdoraAccessToken | None = None

        # Start prefetching the token in the background
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(self._prefetch_adora_bearer_token))

        # Register tools
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.checkout_order)
        self.register(self.check_address)
        if self.coupons_enabled:
            self.register(self.validate_coupons)
            self.register(self.get_available_coupons)
        if self.loyalty_enabled:
            self.register(self.get_loyalty_info)
        self.register(self.get_last_order_status)
        self.register(self.get_menu_item_info)

        # Create query engine and query messages tool
        self.query_engine = _query_engine.create_query_engine(self.namespace)
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

    def _prefetch_adora_bearer_token(self) -> AdoraAccessToken | None:
        """
        Prefetches the Adora bearer token without LLMObs tracking.
        This is called during initialization to start token fetching in the background.

        Returns:
            AdoraAccessToken | None: The bearer token or None if fetching failed
        """
        if not self._adora_bearer_token:
            logger.debug("Prefetching Adora bearer token")
            self._adora_bearer_token = self._fetch_adora_bearer_token()
        return self._adora_bearer_token

    def _get_adora_bearer_token(self) -> AdoraAccessToken | None:
        """
        Gets the Adora bearer token with LLMObs task tracking.
        This should be used during tool methods that need observation.

        Returns:
            AdoraAccessToken | None: The bearer token or None if fetching failed
        """
        if not self._adora_bearer_token:
            logger.debug("Fetching Adora bearer token with LLMObs tracking")
            with LLMObs.task(name="get_adora_bearer_token"):
                self._adora_bearer_token = self._fetch_adora_bearer_token()
        return self._adora_bearer_token

    def _fetch_adora_bearer_token(self) -> AdoraAccessToken | None:
        """
        Internal method to fetch the token from the Adora API.

        Returns:
            AdoraAccessToken | None: The bearer token or None if fetching failed
        """
        try:
            if self.store_id == ADORA_QA_STORE:
                api_key = get_client_secret_with_fallback("ADORA_API_KEY")
                api_secret = get_client_secret_with_fallback("ADORA_API_SECRET")
            elif self.store_id == ADORA_QA_STORE_2:
                api_key = get_client_secret_with_fallback("ADORA_2_API_KEY")
                api_secret = get_client_secret_with_fallback("ADORA_2_API_SECRET")
            else:
                account_name_raw = self.tool_metadata.account_name

                if not account_name_raw:
                    raise ValueError("`tool_metadata.account_name` is missing")

                account_name = re.sub(r"[^a-zA-Z0-9]", "", account_name_raw).upper()

                api_key = get_client_secret_with_fallback(
                    f"{account_name}_ADORA_API_KEY"
                )
                api_secret = get_client_secret_with_fallback(
                    f"{account_name}_ADORA_API_SECRET"
                )

                logger.debug(
                    f"[AdoraTool._fetch_adora_bearer_token] Getting key and secret for account {account_name}. API key: {api_key}. API secret last 2 characters: {api_secret[-2:]}"
                )

            bearer_token = _apis.get_adora_pos_auth_token(
                api_key,
                api_secret,
                qa_store=self.qa_store,
                token_api_endpoint=self.token_api_endpoint,
            )
            return bearer_token
        except Exception as e:
            logger.error(f"Error fetching Adora bearer token: {e}")
            return None

    @tool
    def check_online_ordering_status(self) -> str:
        """
        Check the online ordering status of the store.

        Args:
            None

        Returns:
            str: The online ordering status of the store.
        """
        # For test store, we always return "active" status
        if self.store_id == "9WHCV":
            return "The store is open for online ordering."

        try:
            # Use _get_adora_bearer_token to ensure LLMObs tracking
            bearer_token = self._get_adora_bearer_token()
            if not bearer_token:
                return (
                    "Failed to authenticate ordering tool. Please reach out to our "
                    "support team at help@palona.ai for assistance."
                )

            status = _apis.get_online_ordering_status(
                bearer_token,
                self.store_id,
                qa_store=self.qa_store,
                general_api_endpoint=self.general_api_endpoint,
            )

            if not status:
                raise ValueError(f"Returned invalid online store status: {status}")

            return status

        except Exception as e:
            logger.error(
                "[AdoraTool.check_online_ordering_status] "
                f"Error in checking online ordering status: {e}"
            )
            return "Failed to check the online ordering status, please try again."

    @tool
    def get_store_info(self, date: str) -> str:
        """
        Retrieves store details for the current date, including estimated wait times,
        business hours, and accepted payment methods.

        Args:
            date (str): The current date in yyyy-MM-dd format.

        Returns:
            str: Store details including:
                - Store name, address, and phone number.
                - Estimated wait times for delivery, dine-in, and takeout.
                - Business hours for delivery and pickup.
                - Accepted payment methods for dine-in, takeout, and delivery.
        """
        try:
            if not _utils.is_valid_date(date):
                return f"The date {date} is invalid."

            # Enforce that only current date is allowed
            current_date = datetime.now().strftime("%Y-%m-%d")
            if date != current_date:
                return (
                    f"This tool can only be used for the current date ({current_date})."
                )

            # If store info is already cached return it
            if self.cached_store_info:
                return self.cached_store_info

            # Use _get_adora_bearer_token to ensure LLMObs tracking
            bearer_token = self._get_adora_bearer_token()
            if not bearer_token:
                return (
                    "Failed to authenticate ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            store_info = _apis.get_store_info(
                bearer_token,
                self.store_id,
                date,
                qa_store=self.qa_store,
                general_api_endpoint=self.general_api_endpoint,
            )

            if not store_info:
                raise ValueError(f"Returned invalid wait time: {store_info}")

            # Cache store info
            self.cached_store_info = store_info
            return store_info

        except Exception as e:
            logger.error(f"[AdoraTool.store_info] Error getting store info: {e}")
            return "Failed to get the wait time, please try again."

    @tool
    def check_address(self, address: str) -> str:
        """
        This tool can be used to validate whether or not an address is within a
        delivery zone. Call this tool whenever you need to confirm if a certain
        delivery address can be delivered to.

        Args:
            address (str): A complete **physical street address** (e.g., "123 Main St, Springfield, IL 62704").
                This must **not include phone numbers**, names, or unrelated info.
        Returns:
            str: If the address is valid and within the delivery zone.
        """
        if not address:
            return "Could you provide your address?"

        delivery_address = _llm.llm_call(
            system_prompt="Extract the address into the given output format.",
            prompt=address,
            response_format=DeliveryAddress,
            openai=False,
        )

        if not isinstance(delivery_address, DeliveryAddress):
            return (
                "Failed to identify address. "
                "Please try again by providing the full address."
            )

        validate_order_success, validate_order_message = self._validate_address(
            delivery_address  # type: ignore
        )

        logger.debug(
            f"Validated order: {validate_order_success}\n"
            f"Validate order message: {validate_order_message}"
        )

        return validate_order_message

    @task
    def _validate_address(
        self, canonical_address: DeliveryAddress | None
    ) -> tuple[bool, str]:
        """
        Validates if an address can be delivered to.

        Args:
            canonical_address: The address to validate in DeliveryAddress format

        Returns:
            tuple[bool, str]: (is_valid, message)
        """
        # Use the latitude and longitude to get Adora API call (old Jimmy)
        if not canonical_address:
            logger.warning("[AdoraTool._validate_address] Canonical address is None")
            return (
                False,
                "Could you provide your complete address?",
            )

        # Use _get_adora_bearer_token to ensure LLMObs tracking
        bearer_token = self._get_adora_bearer_token()
        if not bearer_token:
            return (
                False,
                (
                    "Failed to authenticate ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                ),
            )

        # Build payload for address validation
        payload, message = _utils.build_validate_address_payload(
            self.store_id, canonical_address
        )
        if not payload:
            return False, message

        # Validate the address
        validated_address_success, validated_address = _apis.validate_address(
            bearer_token,
            payload,
            qa_store=self.qa_store,
            general_api_endpoint=self.general_api_endpoint,
        )
        logger.debug(f"Validated address: {validated_address}")

        if not validated_address_success:
            return False, "Address is not in the delivery zone."
        else:
            return True, "Address is validated and is in the delivery zone."

    @retrieval
    def _get_relevant_docs(self, chat_history: str) -> str:
        # Decompose chat history into multiple sub-queries

        sub_queries = _llm.llm_call(
            system_prompt=self.backdoor_tool_prompt.get(
                "order_item_prompt", _llm.RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT
            ),
            prompt=chat_history,
            response_format=SubQueries,
            openai=False,
        )

        if not isinstance(sub_queries, SubQueries):
            return "Failed to identify the items the user ordered in the conversation."

        logger.debug(f"Sub-queries identified: {sub_queries.queries}")

        async def run_all_queries():
            tasks = [
                asyncio.create_task(self.query_engine.aquery(query))
                for query in sub_queries.queries
            ]
            try:
                return await asyncio.gather(*tasks)
            except Exception:
                # Cancel remaining tasks
                for task in tasks:
                    if not task.done():
                        task.cancel()
                # Wait for all tasks to complete cancellation (optional)
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

        # Use asyncio.run for a simple async execution without need for manual event loop management
        try:
            results = asyncio.run(run_all_queries())
        except Exception as e:
            logger.error(f"Error executing queries: {e}")
            results = []

        context = ""
        output_data = []
        doc_id = 0
        for res in results:
            for node in res.source_nodes:
                if node.metadata:
                    context += (
                        f"<document index='{doc_id}'>\n"
                        "\t<document_content>\n"
                        f"\t\t{node.text}\n"
                        "\t</document_content>\n"
                        "</document>\n\n"
                    )
                    output_data.append({"id": node.id_, "text": node.text})
                    doc_id += 1

        LLMObs.annotate(input_data=chat_history, output_data=output_data)
        return context

    @task(name="_save_order_to_db")
    def _save_order_to_db(
        self, order: Order, validated_order: AdoraOrderCalculationResult
    ) -> None:
        """
        Save order information to the database.

        Args:
            order: The order object containing order details
            validated_order: The validated order response from Adora API

        Raises:
            Exception: If there is an error saving the order to the database
        """
        # Create a new database session using the project's session factory
        session = SyncSessionLocal()
        try:
            # Get customer phone number safely
            user_phone = ""
            if order.customer and order.customer.phone_number:
                user_phone = order.customer.phone_number

            # Create a new order record
            db_order = DBOrder(
                user_phone_number=user_phone,
                store_phone_number="PLACE_HOLDER",
                order_number=str(validated_order.key) if validated_order.key else "",
                transaction_id=(
                    str(validated_order.key) if validated_order.key else ""
                ),  # Using order key as transaction_id
                store_id=self.store_id,
                tracking_link=None,  # Tracking link will be updated later when available
                status="pending",
                vendor=IntegrationProvider.adora,
                order_date=datetime.now(),
            )

            # Add and commit the order
            session.add(db_order)
            session.commit()
            logger.debug(
                f"[AdoraTool._save_order_to_db] Saved order to database: {db_order.id}"
            )

            # Also save to transactions table for enhanced tracking
            try:
                transaction_id = save_order(
                    tool_metadata=self.tool_metadata,
                    vendor=IntegrationProvider.adora,
                    order_id=(str(validated_order.key) if validated_order.key else ""),
                    store_id=self.store_id,
                    status="pending",
                    fulfillment_strategy=order.order_type,
                    subtotal=(
                        validated_order.subTotal
                        if getattr(validated_order, "subTotal", None) is not None
                        else None
                    ),
                    order_items=order.order_items if order.order_items else None,
                    order_time=datetime.now(),
                    session=session,  # Reuse the same session
                )
                if transaction_id:
                    logger.debug(
                        f"[AdoraTool._save_order_to_db] Saved transaction to database: {transaction_id}"
                    )
            except Exception as transaction_error:
                # Log transaction save error but don't fail the entire operation
                logger.warning(
                    f"[AdoraTool._save_order_to_db] Failed to save transaction data: {transaction_error}",
                    exc_info=True,
                )
        except Exception as e:
            session.rollback()
            logger.error("[AdoraTool._save_order_to_db] Error saving order", exc_info=e)
            raise  # Re-raise the exception to be handled by the caller
        finally:
            session.close()

    @task(name="_fulfill_order [via Adora API]")
    def _fulfill_order(self, order: Order, bearer_token: AdoraAccessToken) -> str:
        payload = order.model_dump_json(by_alias=True)
        LLMObs.annotate(input_data=order, metadata={"payload": payload})

        # Guaranteed phone number since we validated it in the order
        json_payload = json.loads(payload)
        phone_number = json_payload["customer"]["phone"]
        if not phone_number or not _utils.is_valid_phone_number(phone_number):
            return (
                f"{phone_number} is not a valid phone number. "
                "Please provide a valid phone number in the standard ten-digit format."
            )

        if self.qa_store:  # Do not apply discount for QA store
            payload = json.dumps(json_payload)

        validated_order = _apis.validate_order(
            bearer_token=bearer_token,
            payload=payload,
            qa_store=self.qa_store,
            general_api_endpoint=self.general_api_endpoint,
        )

        logger.debug(f"[AdoraTool.checkout_order] Validated order: {validated_order}")

        if not validated_order or not validated_order.key:
            return "Failed to validate order. Please try again."

        # Attempt to save order to database
        try:
            self._save_order_to_db(order, validated_order)
        except Exception as e:
            logger.error(
                "[AdoraTool._fulfill_order] Failed to save order to database, continuing with order fulfillment despite DB save failure",
                exc_info=e,
            )

        text_payment_url = validated_order.paymentUrl

        output = (
            f"Your order is pending!\n"
            "Please head to the payment url to finalize your order!\n"
            f"{text_payment_url}\n\n"
            "Order Summary:\n"
            f"{order.order_items}\n\n"
            f"Subtotal: {validated_order.subTotal}\n"
            f"Sales Tax: {validated_order.taxAmount}\n"
        )

        if (
            order.order_type == AdoraOrderType.DELIVERY
            and validated_order.deliveryCharge
        ):
            output += f"Delivery Fee: {validated_order.deliveryCharge}\n"

        if validated_order.discount and validated_order.discount > 0.0:
            output += f"Discount: {validated_order.discount}\n"

        output += f"Order Total: {validated_order.total}\n"

        output += (
            "\n\nYou MUST include the EXACT payment url in your response:\n"
            f"{text_payment_url}"
        )

        LLMObs.annotate(output_data=output)
        return output

    @task(name="_add_loyalty_discounts")
    def _add_loyalty_discounts(
        self, order: Order, bearer_token: AdoraAccessToken
    ) -> None:
        """
        Adds loyalty discounts to the order if the customer is a loyalty member.

        Args:
            order: The order to add loyalty discounts to
            bearer_token: The Adora API authentication token
        """
        try:
            logger.debug("Starting _add_loyalty_discounts method")
            if not order.customer or not order.customer.phone_number:
                logger.debug(
                    "No customer or phone number found, skipping loyalty discounts"
                )
                return

            # Get and parse customer loyalty data directly
            logger.debug(
                f"Getting loyalty info for customer: {order.customer.phone_number}"
            )
            # Get customer loyalty information
            customer_loyalty_info = _apis.get_customer_info(
                bearer_token,
                self.store_id,
                order.customer.phone_number,
                qa_store=self.qa_store,
                reformat=False,  # Do not reformat the customer info, return the raw pydantic object
                general_api_endpoint=self.general_api_endpoint,
            )

            if not customer_loyalty_info:
                logger.debug("No customer loyalty info found")
                return

            logger.debug("Parsing customer loyalty data")
            # Ensure customer_data is a dictionary
            if isinstance(customer_loyalty_info, str):
                customer_data = json.loads(customer_loyalty_info)
            else:
                # If it's an AdoraCustomerInfo object, convert to dict
                customer_data = json.loads(
                    json.dumps(customer_loyalty_info, default=lambda o: o.__dict__)
                )

            # Only proceed if customer is a loyalty member
            is_loyalty_member = customer_data.get("loyaltyMember", False)
            logger.debug(f"Customer loyalty status: {is_loyalty_member}")
            if not is_loyalty_member:
                logger.debug(
                    "Customer is not a loyalty member, skipping loyalty discounts"
                )
                return

            logger.debug("Customer is a loyalty member, adding loyalty discounts")
            logger.debug("Initializing loyalty discounts")

            # Initialize loyalty_discounts if not already present
            if not hasattr(order, "loyalty_discounts") or not order.loyalty_discounts:
                order.loyalty_discounts = []

            # Add various types of discounts
            self._add_loyalty_rewards(order, customer_data)
            self._add_next_order_credits(order, customer_data)
            self._add_loyalty_offers(order, customer_data)

            logger.debug(
                f"Finished adding loyalty discounts: {order.loyalty_discounts}"
            )
        except Exception as e:
            logger.warning(f"Error adding loyalty discounts: {e}")
            # Continue without loyalty discounts if there's an error

    def _add_loyalty_rewards(self, order: Order, customer_data: dict) -> None:
        """
        Add customer rewards to the order.

        Args:
            order: The order to add loyalty discounts to
            customer_data: Customer loyalty data
        """
        if not hasattr(order, "loyalty_discounts") or order.loyalty_discounts is None:
            order.loyalty_discounts = []

        logger.debug("Checking for customer rewards")
        customer_rewards = customer_data.get("customerRewards", [])
        if customer_rewards:
            logger.debug(f"Found customer rewards: {len(customer_rewards)}")
            for reward in customer_rewards:
                if (
                    isinstance(reward, dict)
                    and "rewardId" in reward
                    and "couponId" in reward
                ):
                    logger.debug(
                        f"Adding reward: {reward['rewardId']}, coupon: {reward['couponId']}"
                    )
                    order.loyalty_discounts.append(
                        LoyaltyReward(
                            coupon_id=reward["couponId"],
                            reward_id=reward["rewardId"],
                        )
                    )

    def _add_next_order_credits(self, order: Order, customer_data: dict) -> None:
        """
        Add next order credits to the order.

        Args:
            order: The order to add loyalty discounts to
            customer_data: Customer loyalty data
        """
        if not hasattr(order, "loyalty_discounts") or order.loyalty_discounts is None:
            order.loyalty_discounts = []

        logger.debug("Checking for customer next order credits")
        customer_credits = customer_data.get("customerNextOrderCredits", [])
        if customer_credits:
            logger.debug(f"Found customer next order credits: {len(customer_credits)}")
            for credit in customer_credits:
                if isinstance(credit, dict):
                    # Check for both CreditId and credit_id field variations
                    logger.debug(f"Credit: {credit}")
                    credit_id = None
                    if "CreditId" in credit:
                        credit_id = credit["CreditId"]
                        logger.debug(f"Adding credit with CreditId: {credit_id}")

                    if credit_id:
                        order.loyalty_discounts.append(
                            LoyaltyNextOrderCredit(
                                credit_id=(
                                    int(credit_id)
                                    if isinstance(credit_id, str)
                                    and credit_id.isdigit()
                                    else (
                                        int(credit_id)
                                        if isinstance(credit_id, (int, float))
                                        else 0
                                    )
                                )
                            )
                        )

    def _add_loyalty_offers(self, order: Order, customer_data: dict) -> None:
        """
        Add loyalty offers to the order.

        Args:
            order: The order to add loyalty discounts to
            customer_data: Customer loyalty data
        """
        if not hasattr(order, "loyalty_discounts") or order.loyalty_discounts is None:
            order.loyalty_discounts = []

        logger.debug("Checking for customer offers")
        customer_offers = customer_data.get("customerOffers", {})
        if customer_offers:
            self._add_offer_codes(order, customer_offers)
            self._add_offer_coupons(order, customer_offers)

    def _add_offer_codes(self, order: Order, customer_offers: dict) -> None:
        """
        Add offer codes to the order.

        Args:
            order: The order to add loyalty discounts to
            customer_offers: Customer offer data
        """
        if not hasattr(order, "loyalty_discounts") or order.loyalty_discounts is None:
            order.loyalty_discounts = []

        codes_list = customer_offers.get("codes", [])
        if codes_list:
            logger.debug(f"Found offer codes: {len(codes_list)}")
            for code in codes_list:
                if (
                    isinstance(code, dict)
                    and "couponId" in code
                    and "couponCode" in code
                ):
                    logger.debug(
                        f"Adding offer code: coupon ID {code['couponId']}, code {code['couponCode']}"
                    )
                    order.loyalty_discounts.append(
                        LoyaltyOffer(
                            coupon_id=code["couponId"],
                            coupon_code=code["couponCode"],
                        )
                    )
        else:
            logger.debug("No offer codes found")

    def _add_offer_coupons(self, order: Order, customer_offers: dict) -> None:
        """
        Add offer coupons to the order.

        Args:
            order: The order to add loyalty discounts to
            customer_offers: Customer offer data
        """
        if not hasattr(order, "loyalty_discounts") or order.loyalty_discounts is None:
            order.loyalty_discounts = []

        coupons_list = customer_offers.get("coupons", [])
        codes_list = customer_offers.get("codes", [])

        if coupons_list:
            logger.debug(f"Found coupons: {len(coupons_list)}")
            for coupon in coupons_list:
                if isinstance(coupon, dict) and "couponId" in coupon:
                    coupon_id = coupon["couponId"]
                    coupon_name = coupon.get("name", "Unnamed coupon")
                    logger.debug(f"Adding coupon: ID {coupon_id}, name {coupon_name}")

                    # For coupons without codes, we need to use the coupon_id but can leave coupon_code empty
                    # Look for matching code in codes_list first
                    matching_code = None
                    for code in codes_list:
                        if (
                            isinstance(code, dict)
                            and code.get("couponId") == coupon_id
                            and "couponCode" in code
                        ):
                            matching_code = code["couponCode"]
                            break

                    order.loyalty_discounts.append(
                        LoyaltyOffer(
                            coupon_id=coupon_id,
                            coupon_code=matching_code
                            or "",  # Use matching code or empty string
                        )
                    )
        else:
            logger.debug("No coupons found")

    @tool
    def checkout_order(self) -> str:
        """
        Validates an order for checkout by extracting structured ordering data from chat history. This function absolutely must be invoked  either when the order is ready to be placed or when the user asks to checkout, pay, place the order, etc.

        Args:
            None

        Returns:
            str: The checkout order details including the payment URL.
        """
        try:
            # fmt: off
            chat_history: str = self.query_messages_tool.query_messages()  # type: ignore
            # fmt: on

            context = self._get_relevant_docs(chat_history)  # type: ignore

            # Get prompt overrides or defaults
            system_prompt = self.backdoor_tool_prompt.get(
                "system_prompt", _llm.EXTRACTOR_SYSTEM_PROMPT
            )
            user_prompt_template = self.backdoor_tool_prompt.get(
                "user_prompt", _llm.EXTRACTOR_USER_PROMPT
            )

            order = _llm.llm_call(
                system_prompt=system_prompt,
                prompt=user_prompt_template.format(
                    context=context, chat_history=chat_history
                ),
                response_format=Order,
                openai=False,
            )

            if not isinstance(order, Order):
                logger.warning(
                    f"`order` object in type {type(order)} but expected type Order.\n"
                    f"`order` object: {order}"
                )
                if isinstance(order, str):
                    order = Order.model_validate(json.loads(order))
                else:
                    return "Failed to extract structured data. Please try again."

            if not order.order_type:
                logger.debug("No order type specified.")
                return "Sorry, do you want that for Takeout or Delivery?"

            try:
                # Adora requires a string 'Delivery' or 'TakeOut' as the order type
                order.order_type = _utils.validate_order_type(order.order_type)
            except Exception as e:
                logger.warning(f"Could not validate order type: {e}")
                return "Sorry, do you want that for Takeout or Delivery?"

            # Validate the address if the order is for delivery
            if order.order_type == AdoraOrderType.DELIVERY:
                if not order.delivery_address:
                    logger.debug(
                        "AdoraTool.checkout_order] Delivery order constructed has no address"
                    )
                    return "Could you provide your address?"
                validate_order_success, validate_order_message = self._validate_address(
                    order.delivery_address  # type: ignore
                )

                if not validate_order_success:
                    return validate_order_message

            # If promise_date_time is set, validate its format and turn into UTC format
            if order.promise_date_time:
                try:
                    # Lazy import
                    from zoneinfo import ZoneInfo

                    # Parse the datetime string
                    parsed_dt = datetime.strptime(
                        order.promise_date_time, "%Y-%m-%dT%H:%M:%S"
                    )

                    # Use tool_metadata timezone or fallback to America/Los_Angeles
                    tz_str = self.tool_metadata.timezone or "America/Los_Angeles"
                    local_tz = ZoneInfo(tz_str)

                    # Localize to store timezone and convert to UTC
                    local_dt = parsed_dt.replace(tzinfo=local_tz)
                    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))

                    # Update order with UTC time
                    order.promise_date_time = utc_dt.strftime("%Y-%m-%dT%H:%M:%S")

                    logger.debug(
                        f"[AdoraTool.checkout_order] Converted promise_date_time from {tz_str} to UTC: {order.promise_date_time}"
                    )
                except ValueError as e:
                    logger.error(
                        f"[AdoraTool.checkout_order] Invalid promise_date_time format: {e}"
                    )
                    return "Invalid time format. Please provide time as: YYYY-MM-DDTHH:MM:SS (e.g., 2024-12-25T14:30:00)"
                except Exception as e:
                    logger.error(
                        f"[AdoraTool.checkout_order] Error converting promise_date_time: {e}"
                    )
                    return f"Error processing promise time: {str(e)}"

            # Validate coupon codes mentioned by the user
            # NOTE: for now, include only the last single valid coupon code even if there are multiple coupon codes mentioned in the chat history, later we may want to include multiple coupon codes
            if order.coupon_codes and self.coupons_enabled:
                code = order.coupon_codes[-1]

                # Use _get_adora_bearer_token to ensure LLMObs tracking
                bearer_token = self._get_adora_bearer_token()
                if bearer_token:
                    # Validate each coupon code

                    result = _apis.validate_coupon_code(
                        bearer_token,
                        self.store_id,
                        code,
                        qa_store=self.qa_store,
                        general_api_endpoint=self.general_api_endpoint,
                    )
                    if result and result.get("isValid", False) and "couponId" in result:
                        if order.coupon_ids:
                            order.coupon_ids.append(result["couponId"])
                        else:
                            order.coupon_ids = [result["couponId"]]
                    else:
                        logger.debug(
                            f"Invalid coupon code: {code} with result: {result}"
                        )

            if self.default_coupon_id:
                if order.coupon_ids:
                    order.coupon_ids.append(self.default_coupon_id)
                else:
                    order.coupon_ids = [self.default_coupon_id]

            # Use _get_adora_bearer_token to ensure LLMObs tracking
            bearer_token = self._get_adora_bearer_token()
            if not bearer_token:
                return (
                    "Failed to authenticate ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            # Override store id
            order.store_id = self.store_id

            ### Validate and check fields ###
            if not order.customer:
                logger.debug("Customer info is missing.")
                return "We'll need your first name and phone number to place the order."
            elif not order.customer.first_name:
                logger.debug("Customer first name is missing.")
                return "We'll need your first name."
            elif not order.customer.phone_number:
                logger.debug("Customer phone number is missing.")
                return "We'll need your phone number."

            # Set user's last name
            # If the account name is "pizzamyheart", append "(via Jimmy)" to the last name; otherwise, append VIA_AGENT_SUFFIX
            via_text = (
                "(via Jimmy)"
                if self.tool_metadata.account_name == "pizzamyheart"
                else VIA_AGENT_SUFFIX
            )
            last_name_parts = []
            if order.customer.last_name:
                last_name_parts.append(order.customer.last_name)
            last_name_parts.append(via_text)
            order.customer.last_name = " ".join(last_name_parts)

            # Set email to default if empty or if it is not valid
            email = order.customer.email
            if not email or not _utils.is_valid_email(email):
                if self.tool_metadata.account_name == "pizzamyheart":
                    order.customer.email = "jimmythesurfer@palona.ai"
                else:
                    order.customer.email = "orderingagent@palona.ai"

            # If order comment is None, set it to an empty string
            order.order_comment = "" if not order.order_comment else order.order_comment

            # Add loyalty discounts to the order
            if self.loyalty_enabled:
                self._add_loyalty_discounts(order, bearer_token)

            logger.debug(f"Extracted structured order: {order}")
            return self._fulfill_order(order, bearer_token)

        except Exception as e:
            logger.warning(f"Error in extracting structured data: {e}")
            logger.warning(traceback.format_exc())
            return "Please try again."

    @tool
    def validate_coupons(self, coupon_codes: List[str]) -> str:
        """
        Validates one or more coupon codes and returns information about their validity.

        This tool should be used when:
        - A customer asks if one or more coupon codes are valid
        - A customer provides one or more coupon codes
        - You need to check the details of specific coupon codes
        - You need to verify discounts before applying them to an order

        Args:
            coupon_codes (List[str]): List of coupon codes to validate.

        Returns:
            str: Information about each coupon code including whether it's valid,
                 its description, and any relevant details or error messages.
                 Lists which codes are valid and which are invalid.
        """
        logger.debug(f"Validating coupon codes: {coupon_codes}")
        if not coupon_codes:
            return "Please provide at least one coupon code to validate."

        codes = list({code.strip() for code in coupon_codes if code and code.strip()})

        # check if all codes in the list are empty strings or only contain whitespace
        if not codes:
            return "Please provide at least one valid coupon code to validate."

        try:
            # Use _get_adora_bearer_token to ensure LLMObs tracking
            bearer_token = self._get_adora_bearer_token()
            if not bearer_token:
                return (
                    "Failed to authenticate ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            results = ["Present all the details in the following validation results:"]

            for code in codes:
                result = _apis.validate_coupon_code(
                    bearer_token,
                    self.store_id,
                    code,
                    qa_store=self.qa_store,
                    general_api_endpoint=self.general_api_endpoint,
                )

                if not result:
                    results.append(f"Failed to validate coupon code: {code}")
                    continue

                if result.get("isValid", False):
                    results.append(
                        f"Coupon code '{code}' is valid;"
                        f"description: {result.get('description', 'No description available')}"
                    )

                else:
                    results.append(
                        f"Coupon code '{code}' is not valid. {result.get('message', '')}"
                    )

            return "\n".join(results)

        except Exception as e:
            logger.error(
                f"[AdoraTool.validate_coupons] Error validating coupon code(s): {e}"
            )
            return "There was an error validating the coupon code(s). Please try again."

    @tool
    def get_loyalty_info(self, phone_number: str) -> str:
        """
        Access customer information and retrieve their loyalty status through phone number

        This tool should be used when:
        - A customer asks about his information recorded in the store
        - A customer asks about their loyalty program status
        - A customer provides their phone number

        Args:
            phone_number (str): The customer's phone number.

        Returns:
            str: Customer information including loyalty status, available rewards,
                 pending offers, and any credits. Returns an error message if the customer
                 cannot be found or if there's an issue with the API.
        """
        error_message = (
            "There was an error retrieving your loyalty information. Please try again."
        )

        try:
            phone_number = _utils.format_phone_number(phone_number)
            if not phone_number:
                return "Please provide a valid phone number in the standard ten-digit format."

            # Use _get_adora_bearer_token to ensure LLMObs tracking
            bearer_token = self._get_adora_bearer_token()
            if not bearer_token:
                logger.debug("[AdoraTool.get_loyalty_info] No bearer token found")
                return error_message

            customer_info = _apis.get_customer_info(
                bearer_token,
                self.store_id,
                phone_number,
                qa_store=self.qa_store,
                general_api_endpoint=self.general_api_endpoint,
            )

            if customer_info is None:
                return "Failed to retrieve customer information. Please try again."

            # Ensure we return a string
            if not isinstance(customer_info, str):
                customer_info = json.dumps(customer_info, default=lambda o: o.__dict__)

            return customer_info

        except Exception as e:
            logger.error(
                f"[AdoraTool.get_loyalty_info] Error validating loyalty status: {e}"
            )
            return error_message

    @tool
    def get_last_order_status(self, phone_number: str) -> str:
        """
        Retrieves the status of the customer's last order using their phone number.

        This tool should be used when:
        - A customer asks about their most recent order status
        - A customer wants to track their latest order
        - A customer provides their phone number to check order history

        Args:
            phone_number (str): The customer's phone number.

        Returns:
            str: Information about the customer's last order status including order details,
                 current status, and any relevant tracking information. Returns an error message
                 if the customer cannot be found or if there's an issue with the API.
        """
        error_message = (
            "There was an error retrieving your order status. Please try again."
        )

        try:
            phone_number = _utils.format_phone_number(phone_number)
            if not phone_number:
                return "Please confirm your phone number."

            # Use _get_adora_bearer_token to ensure LLMObs tracking
            bearer_token = self._get_adora_bearer_token()
            if not bearer_token:
                logger.debug("[AdoraTool.get_last_order_status] No bearer token found")
                return error_message

            # Get customer's latest order
            logger.debug(f"Getting last order status for phone number: {phone_number}")

            latest_order = _apis.get_customer_latest_order(
                bearer_token,
                phone_number,
                qa_store=self.qa_store,
                general_api_endpoint=self.general_api_endpoint,
            )

            if latest_order is None:
                return "No recent orders found for this phone number. Please double check your phone number and try again."

            # Format the response based on the available information
            return self._format_order_status(latest_order)

        except Exception as e:
            logger.error(
                f"[AdoraTool.get_last_order_status] Error retrieving order status: {e}"
            )
            return error_message

    def _format_order_status(self, latest_order: AdoraLatestOrderResponse) -> str:
        """
        Format the latest order response into a user-friendly string.

        Args:
            latest_order: AdoraLatestOrderResponse object containing order information

        Returns:
            str: Formatted order status information
        """
        try:
            formatted_info = ""

            # Extract process status from order detail
            if latest_order.orderDetail and latest_order.orderDetail.processStatus:
                formatted_info += (
                    f"Order Status: {latest_order.orderDetail.processStatus}\n"
                )
            else:
                formatted_info += "Order Status: Unknown\n"

            # Add tracker URL if available
            if latest_order.trackerURL:
                formatted_info += (
                    f"\nYou can track your order here:\n{latest_order.trackerURL}\n"
                )
            else:
                formatted_info += "\nNo tracking information available.\n"

            return formatted_info

        except Exception as e:
            logger.error(
                f"[AdoraTool._format_order_status] Error formatting order status: {e}"
            )
            return "Error formatting order status information."

    @tool
    def get_menu_item_info(self, menu_item: str) -> str:
        """
        Get details about a menu item. The detailed information such as modifiers, toppings, etc. could be found by this tool.
        This tool should be used when:
        - A customer asks about a specific menu item
        - A customer wants to add modifiers or toppings to a menu item
        - A customer wants to select a flavor/sauce for a menu item

        Do not use this tool if the customer is asking about the menu in general or when user checks out.

        Args:
            menu_item (str): The name of the menu item to get information about

        Returns:
            str: Information about the menu item
        """
        if not menu_item or not menu_item.strip():
            return "Please specify a menu item to get information about."

        try:
            logger.debug(f"Getting menu item info for: {menu_item}")
            menu_item_info = self.query_engine.query(menu_item.strip())
            context = []
            for node in menu_item_info.source_nodes:
                if node.metadata:
                    context.append(node.text)

            if not context:
                return f"No information found for menu item: {menu_item}"

            return "----\n".join(context)
        except Exception as e:
            logger.error(
                f"[AdoraTool.get_menu_item_info] Error getting menu item info: {e}"
            )
            return "Failed to retrieve menu item information. Please try again."

    @tool
    def get_available_coupons(self) -> str:
        """
        Retrieves all currently available coupons from the Adora API.

        This tool should be used when:
        - A customer asks about available promotions or discounts
        - A customer wants to see what coupons are currently valid
        - A customer asks about current deals or specials

        Args:
            None

        Returns:
            str: A list of all available coupons with their details including coupon codes,
                 descriptions, and validity information. Returns an error message if the
                 coupons cannot be retrieved.
        """
        try:
            # Use _get_adora_bearer_token to ensure LLMObs tracking
            bearer_token = self._get_adora_bearer_token()
            if not bearer_token:
                return (
                    "Failed to authenticate ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            available_coupons = _apis.get_available_coupons(
                bearer_token,
                self.store_id,
                qa_store=self.qa_store,
                general_api_endpoint=self.general_api_endpoint,
            )

            if not available_coupons:
                return "No coupons are currently available."

            return available_coupons

        except Exception as e:
            logger.error(
                f"[AdoraTool.get_available_coupons] Error retrieving available coupons: {e}"
            )
            return "There was an error retrieving available coupons. Please try again."
