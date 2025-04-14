import asyncio
import traceback
from functools import cached_property

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, tool

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.toast_tool._apis import (
    get_online_ordering_status,
    get_order_prices,
    get_toast_access_token,
    submit_order,
)
from tools.toast_tool._apis import get_store_info as get_store_info_api
from tools.toast_tool.classes import ToastAccessToken
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

from . import _utils
from ._llm import (
    EXTRACTOR_SYSTEM_PROMPT,
    EXTRACTOR_USER_PROMPT,
    RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
    llm_call,
)
from ._query_engine import create_query_engine
from .classes import Order, SubQueries


class ToastTool(Toolkit):
    def __init__(
        self,
        store_id: str,
        namespace: str,
        tool_metadata: ToolMetadata,
    ):
        super().__init__(name="toast_tool")

        self.store_id = store_id
        self.namespace = namespace
        self.tool_metadata = tool_metadata
        self._cached_store_info: str | None = None

        # Register tools
        self.register(self.check_online_ordering_status)
        self.register(self.get_store_info)
        self.register(self.checkout_order)
        self.register(self.check_address)

        # Retrieval tools
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)

        self.query_engine = create_query_engine(self.namespace)

    @cached_property
    def _toast_bearer_token(self) -> ToastAccessToken | None:
        with LLMObs.task(name="get_toast_bearer_token"):
            api_key = get_client_secret_with_fallback("TOAST_QA_API_KEY")
            api_secret = get_client_secret_with_fallback("TOAST_QA_API_SECRET")
            bearer_token = get_toast_access_token(api_key, api_secret, True)
            return bearer_token

    @tool
    def get_store_info(self) -> str:
        """
        Retrieves detailed configuration information for a specific restaurant.

        Returns:
            str: A JSON-formatted string containing:
                - Basic restaurant information (e.g., name, timezone, GUID)
                - Location details such as address and phone number
                - Delivery and online ordering configuration
                - Operating hours and schedule data
                - Prep times and supported web URLs
        """

        try:
            # If store info is already cached return it
            if self._cached_store_info:
                return self._cached_store_info

            if not self._toast_bearer_token:
                return (
                    "Failed to authenticate ordering tool. "
                    "Please reach out to our support team at help@palona.ai "
                    "for assistance."
                )

            store_info = get_store_info_api(
                self._toast_bearer_token, self.store_id
            ).model_dump_json()

            # Cache store info
            self._cached_store_info = store_info
            return store_info

        except Exception as e:
            logger.error(f"[ToastTool.store_info] Error getting store info: {e}")
            return "Failed to get the store information, please try again."

    @tool
    def check_online_ordering_status(self) -> str:
        """
        Retrieves the current online ordering availability status of a specified restaurant.

        Returns:
            str: A JSON-formatted string containing:
            - The restaurant's online ordering availability status
            - The reason why the restaurant is available or unavailable to accept online orders
        """

        try:
            if not self._toast_bearer_token:
                return (
                    "Failed to authenticate ordering tool. Please reach out to our "
                    "support team at help@palona.ai for assistance."
                )

            status = get_online_ordering_status(
                self._toast_bearer_token, self.store_id, True
            ).model_dump_json()

            return status

        except Exception as e:
            logger.error(
                "[ToastTool.check_online_ordering_status] "
                f"Error in checking online ordering status: {e}"
            )
            return "Failed to check the online ordering status, please try again."

    # TODO: Investigate whether Agno agent can handle async tool calling, and whether calling asynio.run in the tool is allowed
    @tool
    async def checkout_order(self, latest_user_message: str) -> str:
        """
        Processes an order checkout.

        Returns:
            str: Order checkout confirmation details
        """
        try:
            # Datadog decorators screw the function signature so use type ignore as workaround
            chat_history: str = self._get_chat_history(latest_user_message)  # type: ignore
            context = self._get_relevant_docs(chat_history)  # type: ignore

            order = llm_call(
                system_prompt=EXTRACTOR_SYSTEM_PROMPT,
                prompt=EXTRACTOR_USER_PROMPT.format(
                    context=context, chat_history=chat_history
                ),
                response_format=Order,
                reasoning=False,
            )

            if not isinstance(order, Order):
                logger.error(
                    f"`order` object in type {type(order)} but expected type Order.\n"
                    f"`order` object: {order}"
                )
                # Checking logs for Adora, always failed the try to construct str to Order
                # Therefore, no need to do it. Let's check the behavior and clean up Adora
                return "Failed to extract structured data. Please try again."

            # Validate and check the order
            error_message = self._post_process_order(order)
            if error_message:
                return error_message

            return self._submit_order(order)

        except Exception as e:
            logger.error(f"Error in submit order: {e}")
            logger.error(traceback.format_exc())
            return "Please try again."

    @tool
    def check_address(self) -> str:
        """
        Validates a delivery address.

        Returns:
            str: Address validation results
        """
        raise Exception("Not Implemented")

    @retrieval
    def _get_chat_history(self, latest_user_message: str) -> str:
        """
        Retrieves the chat history from the query messages tool.

        Args:
            latest_user_message (str): The latest user message to include in the chat history.

        Returns:
            str: A string representing the entire chat history.
        """
        # TODO: The query_messages function returns error messages rather than raising exceptions. There is no generic way to verify the validity of the returned chat_history.
        chat_history: str = self.query_messages_tool.query_messages(latest_user_message)  # type: ignore

        # Basic check for error messages (TEMPORARY workaround)
        error_indicators = [
            "Error in getting chat history",
            "Conversation history not found",
            "Agent session ot found",
        ]
        if any(indicator in chat_history for indicator in error_indicators):
            logger.warning(
                f"[ToastTool._get_chat_history] Possible issue with chat history: {chat_history}"
            )

        LLMObs.annotate(output_data=chat_history)

        return chat_history

    @retrieval
    async def _get_relevant_docs(self, chat_history: str) -> str:
        # TODO: Implement llm_call
        sub_queries = llm_call(
            system_prompt=RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
            prompt=chat_history,
            response_format=SubQueries,
            reasoning=False,
        )

        # Retrieve relevant documents based on the sub-queries
        # TODO: Implement `_query_engine.create_query_engine`
        tasks = [
            asyncio.create_task(self.query_engine.aquery(q))
            for q in sub_queries.queries  # type: ignore
        ]
        results = await asyncio.gather(*tasks)

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

        LLMObs.annotate(
            input_data={"chat_history": chat_history}, output_data=output_data
        )
        return context

    def _post_process_order(self, order: Order) -> str | None:
        """
        Validates and processes an order before submission.

        Args:
            order (Order): The order object to validate and process.

        Returns:
            str | None: Error message if validation fails, None if successful.

        """
        # Check if the order type non-empty and takeout. For now, we only support takeout orders
        if not order.diningOption.behavior:
            logger.error("No order type specified.")
            return "Sorry, do you want that for Takeout? We only support Takeout orders at the moment."

        try:
            order.diningOption.behavior = _utils.validate_order_type(
                order.diningOption.behavior
            )
        except Exception as e:
            logger.error(f"Could not validate order type: {e}")
            return "Sorry, do you want that for Takeout? We only support Takeout orders at the moment."

        # TODO: Validate the address if the order is for delivery
        # PLACEHOLDER: Validate the address if the order is for delivery

        logger.debug(f"Extracted structured data: {order}")
        logger.debug(f"Extracted structured data type: {type(order)}")
        if not self._toast_bearer_token:
            return (
                "Failed to authenticate ordering tool. "
                "Please reach out to our support team at help@palona.ai "
                "for assistance."
            )

        # TODO: Discuss with the team if we want to adopt Adora agent's approach to handling last names and email addresses.
        ### Validate checks ###
        if not order.checks:
            logger.error("Order checks are missing.")
            return "We'll need to check your order to place it."

        # Validate each check in the order
        for check in order.checks:
            if not check.customer:
                logger.error("Customer info is missing.")
                return "We'll need your first name, last name, email, and phone number to place the order."
            if not check.customer.firstName:
                logger.error("Customer first name is missing.")
                return "We'll need your first name."
            if not check.customer.lastName:
                logger.error("Customer last name is missing.")
                return "We'll need your last name."

            ########## NOTE: if we want to append "(via Toast Agent)" to the customer last name ##########

            # check.customer.lastName = (
            #     "(via Toast Agent)"
            #     if not check.customer.lastName
            #     else f"{check.customer.lastName} (via Jimmy)"
            # )
            ##############################################

            email = check.customer.email
            if not email or not _utils.is_valid_email(email):
                logger.error(f"Invalid email address: {email}")
                return "We'll need your email address."

            ########## NOTE: the following is how Adora agent handles the email. ##########
            # Set email to default if empty or if it is not valid
            # email = order.customer.email
            # if not email or not _utils.is_valid_email(email):
            #     order.customer.email = "jimmythesurfer@palona.ai"
            ##############################################

            if not check.customer.phone or not _utils.is_valid_phone_number(
                _utils.format_phone_number(check.customer.phone)
            ):
                logger.error(
                    f"Customer phone number is missing or invalid. Phone: {check.customer.phone}"
                )
                return "We'll need your phone number."

    def _submit_order(self, order: Order) -> str:
        # Retrieve the bearer token
        toast_bearer_token = self._toast_bearer_token
        if not toast_bearer_token:
            return (
                "Failed to authenticate ordering tool. "
                "Please reach out to our support team at help@palona.ai "
                "for assistance."
            )
        # First let toast API fill in the prices
        try:
            order = get_order_prices(toast_bearer_token, self.store_id, order)
            order = submit_order(toast_bearer_token, self.store_id, order)

            # TODO: Decide what messages to return to the user, and whether we want to store the Order guid in the database.
            return (
                f"Order #{order.guid} submitted successfully! "
                f"Your total is ${order.checks[0].totalAmount}. "
                f"Your order will be ready for pickup at {order.estimatedFulfillmentDate}"
            )
        except Exception as e:
            logger.error(f"Failed to submit the order: {e}")
            return "There was an error while submitting the order. Please try again."

    def _validate_address(self, address: str) -> str:
        return "Pending Implementation"
