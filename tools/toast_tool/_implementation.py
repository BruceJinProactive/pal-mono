import asyncio
import json
import traceback
from functools import cached_property

import polyline
from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import retrieval, tool
from pydantic import ValidationError
from shapely import Point, Polygon

from agent.tool import ToolMetadata
from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.toast_tool._apis import (
    get_dining_option,
    get_online_ordering_status,
    get_order_prices,
    get_toast_access_token,
    submit_order,
)
from tools.toast_tool._apis import get_store_info as get_store_info_api
from tools.toast_tool.classes import DeliveryAddress, ToastAccessToken
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

from ._llm import (
    EXTRACTOR_SYSTEM_PROMPT,
    EXTRACTOR_USER_PROMPT,
    RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
    llm_call,
)
from ._query_engine import create_query_engine
from ._utils import (
    add_lat_long_to_address,
    format_phone_number,
    is_valid_email,
    is_valid_phone_number,
    validate_item_modifier_quantity,
    validate_order_type,
)
from .classes import OrderInput, Price, SubQueries


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
        self.register(self.get_store_info_tool)
        self.register(self.checkout_order)
        self.register(self.check_address)

        # Retrieval tools
        self.query_messages_tool = QueryMessagesTool(self.tool_metadata)
        self.query_engine = create_query_engine(self.namespace)

        # TODO: See if the following lines are needed
        # loop = asyncio.get_running_loop()
        # loop.create_task(asyncio.to_thread(lambda: self._toast_bearer_token))

    @cached_property
    def _toast_bearer_token(self) -> ToastAccessToken | None:
        with LLMObs.task(name="get_toast_bearer_token"):
            api_key = get_client_secret_with_fallback("TOAST_CLIENT_ID")
            api_secret = get_client_secret_with_fallback("TOAST_CLIENT_SECRET")
            bearer_token = get_toast_access_token(api_key, api_secret, True)
            return bearer_token

    @tool
    def check_address(self, address: str) -> str:
        """
        Validates if the given address (using x and y coordinates) is within the restaurant's delivery area.
        Retrieves the store information (from cache or API), accesses the delivery area using dot notation,
        decodes the polyline string into a list of Point objects, and creates a Polygon instance.
        Finally, it checks whether the provided point lies inside the polygon area.
        Args:
            address (str): The address to validate.
        Returns:
            str: A message indicating whether the address is within the delivery area.
        """
        # Retrieve store information from cache if available.

        if not address:
            return "Could you provide your address?"

        delivery_address = llm_call(
            system_prompt="Extract the address into the given output format.",
            prompt=address,
            response_format=DeliveryAddress,
            reasoning=False,
        )

        if not isinstance(delivery_address, DeliveryAddress):
            return (
                "Failed to identify address. "
                "Please try again by providing the full address."
            )

        success, message, delivery_address = add_lat_long_to_address(delivery_address)
        if not success:
            return message

        point = Point(delivery_address.lng, delivery_address.lat)
        store_info_str = self.get_store_info()
        if store_info_str == "Failed to get the store information, please try again.":
            return store_info_str
        try:
            store_info = json.loads(store_info_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse store info JSON: {e}")
            return "Failed to process store information."

        polyline_str = (
            store_info["delivery"]["area"]
            if "delivery" in store_info and "area" in store_info["delivery"]
            else None
        )
        if (
            not polyline_str
            or polyline_str == "Failed to get the store information, please try again."
        ):
            return "Delivery area is empty." if not polyline_str else polyline_str

        # Decode the polyline string into a list of Point objects
        try:
            decoded = polyline.decode(polyline_str, geojson=True)
            polygon = Polygon([(lng, lat) for lng, lat in decoded])
        except Exception as e:
            logger.error(f"Decode polyline to points failed: {e}")
            return "Failed to decode the delivery area boundary."

        # Validate the given point against the polygon's area using our helper method
        if polygon.contains(point):
            return "Address is within the delivery area."
        else:
            return "Address is outside the delivery area."

    @tool
    def get_store_info_tool(self) -> str:
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

        return self.get_store_info()

    def get_store_info(self) -> str:
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
    def checkout_order(self, latest_user_message: str) -> str:
        """
        Processes an order checkout.

        Returns:
            str: Order checkout confirmation details
        """
        try:
            order = self._construct_order(latest_user_message)

            # If the order is a string, it indicates an error message
            # In this case, return the error message
            if isinstance(order, str):
                return order

            # Validate and check the order
            error_message = self._post_process_order(order)
            if error_message:
                return error_message

            return self._submit_order(order)

        except Exception as e:
            logger.error(f"Error in submit order: {e}")
            logger.error(traceback.format_exc())
            return "Please try again."

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
    def _get_relevant_docs(self, chat_history: str) -> str:
        # Decompose chat history into multiple sub-queries
        sub_queries = llm_call(
            system_prompt=RETRIEVE_ORDER_ITEMS_SYSTEM_PROMPT,
            prompt=chat_history,
            response_format=SubQueries,
            reasoning=False,
        )

        if not isinstance(sub_queries, SubQueries):
            return "Failed to identify the items the user ordered in the conversation."

        logger.info(f"Sub-queries identified: {sub_queries.queries}")

        # Perform knowledege retrieval on all sub-queries asynchronously
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            query_tasks = asyncio.gather(
                *[self.query_engine.aquery(q) for q in sub_queries.queries]
            )
            results = loop.run_until_complete(query_tasks)
        finally:
            loop.close()
            asyncio.set_event_loop(None)

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

    def _construct_order(self, latest_user_message: str) -> OrderInput | str:
        chat_history: str = self._get_chat_history(latest_user_message)  # type: ignore
        context = self._get_relevant_docs(chat_history)  # type: ignore
        order = llm_call(
            system_prompt=EXTRACTOR_SYSTEM_PROMPT,
            prompt=EXTRACTOR_USER_PROMPT.format(
                context=context, chat_history=chat_history
            ),
            response_format=OrderInput,
            reasoning=False,
        )

        # Check if the order is a string and convert it to an OrderInput object, catching any errors
        try:
            if type(order) is str:
                order = json.loads(order)
                order = OrderInput(**order)

            if not isinstance(order, OrderInput):
                raise ValueError(
                    f"`order` object in type {type(order)} but expected type Order.\n"
                    f"`order` object: {order}"
                )

            return order
        except ValidationError as e:
            logger.warning(e)
            warning_message = ""
            for error in e.errors():
                logger.warning(
                    f"Missing or invalid order data in the response: {error}"
                )
                warning_message += f"Missing or invalid order data in the response: {error['loc'][-1]}: {error['msg']}, input: {error.get('input', 'N/A')}\n"
            return (
                warning_message
                + "\nAsk the customer to provide the missing information or correct the invalid details."
            )
        except Exception as e:
            logger.error(e)
            return f"Failed to construct order: {e}"

    def _post_process_order(self, order: OrderInput) -> str | None:
        """
        Validates and processes an order before submission.

        Args:
            order (OrderInput): The order object to validate and process.

        Returns:
            str | None: Error message if validation fails, None if successful.

        """
        # Check if the order type non-empty and takeout. For now, we only support takeout orders

        if not order.diningOption or not order.diningOption.guid:
            logger.error("Order diningOption is missing or its guid is empty.")
            return "Sorry, do you want that for Takeout? We only support Takeout orders at the moment."

        if not self._toast_bearer_token:
            return (
                "Failed to authenticate ordering tool. "
                "Please reach out to our support team at help@palona.ai "
                "for assistance."
            )
        dining_behavior = get_dining_option(
            self._toast_bearer_token, self.store_id, order.diningOption.guid
        )

        try:
            _ = validate_order_type(dining_behavior.behavior)  # type: ignore
            _ = validate_item_modifier_quantity(order.checks[0].selections)
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
            if not email or not is_valid_email(email):
                logger.error(f"Invalid email address: {email}")
                return "We'll need your email address."

            ########## NOTE: the following is how Adora agent handles the email. ##########
            # Set email to default if empty or if it is not valid
            # email = order.customer.email
            # if not email or not is_valid_email(email):
            #     order.customer.email = "jimmythesurfer@palona.ai"
            ##############################################

            if not check.customer.phone or not is_valid_phone_number(
                format_phone_number(check.customer.phone)
            ):
                logger.error(
                    f"Customer phone number is missing or invalid. Phone: {check.customer.phone}"
                )
                return "We'll need your phone number."

    def _submit_order(self, order: OrderInput) -> str:
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
            # order = get_order_prices(toast_bearer_token, self.store_id, order)
            order = submit_order(toast_bearer_token, self.store_id, order)

            # TODO: Decide what messages to return to the user, and whether we want to store the Order guid in the database.
            logger.info(
                f"Order #{order.guid} submitted successfully! Your total is ${order.checks[0].totalAmount}. Your order will be ready for pickup at {order.estimatedFulfillmentDate}"
            )
            return (
                f"Order #{order.guid} submitted successfully! "
                f"Your total is ${order.checks[0].totalAmount}. "
                f"Your order will be ready for pickup at {order.estimatedFulfillmentDate}"
            )
        except Exception as e:
            logger.error(f"Failed to submit the order: {e}")
            return "There was an error while submitting the order. Please try again."

    def _get_order_prices(self, order: OrderInput) -> str:
        # Retrieve the bearer token
        toast_bearer_token = self._toast_bearer_token
        if not toast_bearer_token:
            return (
                "Failed to authenticate ordering tool. "
                "Please reach out to our support team at help@palona.ai "
                "for assistance."
            )
        try:
            order = get_order_prices(toast_bearer_token, self.store_id, order)
            return Price(
                amount=order.checks[0].amount,
                taxAmount=order.checks[0].taxAmount,
                totalAmount=order.checks[0].totalAmount,
            ).model_dump_json()
        except Exception as e:
            logger.error(f"Failed to get the order prices: {e}")
            return (
                "There was an error while getting the order prices. Please try again."
            )

    @tool
    def get_order_prices_tool(self, latest_user_message: str) -> str:
        try:
            order = self._construct_order(
                latest_user_message,
            )

            # If the order is a string, it indicates an error message
            # In this case, return the error message
            if isinstance(order, str):
                return order

            return self._get_order_prices(order)
        except Exception as e:
            logger.error(f"Error in get order prices: {e}")
            return (
                "There was an error while getting the order prices. Please try again."
            )
