import asyncio
import http.client
import json
import re
import textwrap
import urllib.parse
from typing import Any, Dict, Optional, TypeVar, Union

from ddtrace.llmobs import LLMObs
from pydantic import BaseModel, ValidationError

from agent.tool.internal.query_messages_tool import QueryMessagesTool
from tools.utils.ordering._constants import (
    VALID_DATE_PATTERN,
    VALID_EMAIL_PATTERN,
    VALID_PHONE_PATTERN,
)
from tools.utils.ordering._llm import llm_call
from tools.utils.ordering._query_engine import BaseQueryEngine
from tools.utils.ordering.classes import (
    ApiProvider,
    GenericHubResponse,
    HttpMethod,
    SubQueries,
)
from utils.log import logger

T = TypeVar("T", bound=BaseModel)
S = TypeVar("S", bound=SubQueries)


def get_chat_history(query_messages_tool: QueryMessagesTool) -> str:
    """
    Retrieves the chat history from the query messages tool.

    Returns:
        str: A string representing the entire chat history.
    """
    # TODO: The query_messages function returns error messages rather than raising exceptions. There is no generic way to verify the validity of the returned chat_history.
    chat_history: str = query_messages_tool.query_messages()  # type: ignore

    # Basic check for error messages (TEMPORARY workaround)
    error_indicators = [
        "Error in getting chat history",
        "Conversation history not found",
        "Agent session not found",
    ]
    if any(indicator in chat_history for indicator in error_indicators):
        logger.warning(
            f"[ToastTool._get_chat_history] Possible issue with chat history: {chat_history}"
        )
        raise ValueError(
            f"[ToastTool._get_chat_history] Possible issue with chat history: {chat_history}"
        )

    LLMObs.annotate(output_data=chat_history)

    return chat_history


def get_relevant_docs(
    query_engine: BaseQueryEngine,
    chat_history: str,
    system_prompt: str,
    response_format: type[S],
) -> str:
    """
    Decomposes the chat history into multiple sub-queries and retrieves the relevant documents.

    Args:
        chat_history (str): The chat history to decompose into sub-queries.
        system_prompt (str): The system prompt to use for the LLM call.

    Returns:
        str: The relevant documents.
    """
    # Decompose chat history into multiple sub-queries
    sub_queries = llm_call(
        system_prompt=system_prompt,
        prompt=chat_history,
        response_format=response_format,
        openai=False,
    )

    if not isinstance(sub_queries, response_format):
        return "Failed to identify the items the user ordered in the conversation."

    logger.debug(f"Sub-queries identified: {sub_queries.queries}")

    async def run_all_queries():
        tasks = [
            asyncio.create_task(query_engine.aquery(query))
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
    found_doc_names = set()
    # Iterate through the results and extract relevant information
    for res in results:
        for node in res.source_nodes:
            if node.metadata:
                doc_name = node.metadata["file_name"]

                # Check if the document name is already in the set
                # If it is, skip to the next node
                # If not, add it to the set and process the node
                if doc_name in found_doc_names:
                    continue
                found_doc_names.add(doc_name)

                # Indent the text
                node_text = textwrap.indent(node.text, 2 * "\t")

                context += (
                    f"<document name='{doc_name}'>\n"
                    "\t<document_content>\n"
                    f"{node_text}\n"
                    "\t</document_content>\n"
                    "</document>\n\n"
                )
                output_data.append({"id": node.id_, "text": node.text})

    LLMObs.annotate(input_data=chat_history, output_data=output_data)
    return context


def format_phone_number(phone_number: str) -> str:
    # Remove non-digit characters
    digits = re.sub(r"\D", "", phone_number)

    # Ensure it has 10 digits (remove US country code if present)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]

    # Validate the number has exactly 10 digits
    if len(digits) != 10:
        return ""

    return digits


def is_valid_phone_number(phone_number: str) -> bool:
    return re.match(VALID_PHONE_PATTERN, phone_number) is not None


def is_valid_email(email: str) -> bool:
    return re.match(VALID_EMAIL_PATTERN, email) is not None


def is_valid_date(date: str) -> bool:
    return bool(re.match(VALID_DATE_PATTERN, date))


def construct_order(
    system_prompt: str,
    user_prompt: str,
    response_format: type[T],
    error_prefix: str = "Failed to construct order",
) -> Union[T, str]:
    """
    Constructs an order from LLM output using custom prompts and handles validation errors.

    Args:
        system_prompt: The system prompt to use for the LLM call
        user_prompt: The user prompt to use for the LLM call
        response_format: The Pydantic model class to validate against
        error_prefix: Custom prefix for error messages

    Returns:
        Either a validated instance of response_format or an error message string
    """
    try:

        response = llm_call(
            system_prompt=system_prompt,
            prompt=user_prompt,
            response_format=response_format,
            openai=False,
        )

        if response is None:
            raise ValueError("Response is None")

        if isinstance(response, str):
            parsed_data = json.loads(response)
        elif isinstance(response, dict):
            parsed_data = response
        elif isinstance(response, response_format):
            return response
        else:
            raise ValueError(f"Unexpected response type: {type(response)}")

        result = response_format(**parsed_data)

        logger.debug(f"Constructed order: {result}")
        return result

    except ValidationError as e:
        logger.warning(e)
        warning_message = ""
        for error in e.errors():
            logger.warning(f"Missing or invalid order data in the response: {error}")
            warning_message += f"Missing or invalid order data in the response: {error['loc'][-1]}: {error['msg']}, input: {error.get('input', 'N/A')}\n"
        return (
            warning_message
            + "\nPlease provide the missing information or correct the invalid details."
        )

    except Exception as e:
        logger.error(e)
        return f"{error_prefix}: {e}"


def _build_base_url(
    provider: ApiProvider, qa_store: bool, general_api_endpoint: Optional[str] = None
) -> tuple[str, str]:
    """
    Build the base URL and path for the given provider.

    Args:
        provider: The API provider
        qa_store: Whether to use QA environment (for Adora API)
        general_api_endpoint: Optional custom API endpoint

    Returns:
        tuple[str, str]: (base_url, path_prefix)
    """
    # Handle custom endpoint if provided
    if general_api_endpoint:
        try:
            # Handle cases where scheme might already be included
            if "://" in general_api_endpoint:
                parsed = urllib.parse.urlparse(general_api_endpoint)
                if parsed.scheme != "https":
                    raise ValueError("Only HTTPS endpoints are allowed")
            else:
                parsed = urllib.parse.urlparse(f"https://{general_api_endpoint}")

            if not parsed.netloc:
                raise ValueError("Invalid endpoint format")

        except Exception as e:
            raise ValueError(
                f"Invalid general_api_endpoint: {general_api_endpoint}"
            ) from e

        # Return the netloc only to ensure consistency
        return parsed.netloc, parsed.path if parsed.path else ""

    # Default endpoints for each provider
    if provider == ApiProvider.OLO:
        base_url = "ordering.api.olosandbox.com"
        path_prefix = ""
    elif provider == ApiProvider.ADORA:
        if qa_store:
            base_url = "adora-qa-api-public.azurewebsites.net"
        else:
            base_url = "public.api.adorapos.net"
        path_prefix = "/api/v1/OrderHub/"
    elif provider == ApiProvider.TOAST:
        base_url = "ws-sandbox-api.eng.toasttab.com"
        path_prefix = ""
    else:
        raise ValueError(f"Unsupported API provider: {provider}")

    return base_url, path_prefix


def _build_headers(
    provider: ApiProvider,
    bearer_token: Any,
    store_id: Optional[str],
    extra_headers: Optional[Dict[str, str]],
) -> Dict[str, str]:
    """
    Build headers for the API request.

    Args:
        provider: The API provider
        bearer_token: The access token for the specific API
        store_id: Store ID (required for Toast API)
        extra_headers: Optional additional headers

    Returns:
        Dict[str, str]: Complete headers dictionary
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": bearer_token.get_token_header_value(),
    }

    # Add provider-specific headers
    if provider == ApiProvider.TOAST:
        if not store_id:
            raise ValueError(
                "store_id must be provided when calling Toast APIs (Toast-Restaurant-External-ID header)."
            )
        headers["Toast-Restaurant-External-ID"] = store_id

    # Add any extra headers
    if extra_headers:
        headers.update(extra_headers)

    return headers


def _make_request(
    conn: http.client.HTTPSConnection,
    provider: ApiProvider,
    method_str: str,
    path: str,
    body: str,
    headers: Dict[str, str],
) -> http.client.HTTPResponse:
    """
    Make the HTTP request with provider-specific method validation.

    Args:
        conn: The HTTPS connection object
        provider: The API provider
        method_str: The HTTP method as string
        path: The request path
        body: The request body
        headers: The request headers

    Returns:
        http.client.HTTPResponse: The HTTP response

    Raises:
        ValueError: If the HTTP method is not supported by the provider
    """
    # Make the request based on provider-specific method support
    if provider == ApiProvider.ADORA:
        # Adora only supports GET and POST
        if method_str in ["GET", "POST"]:
            conn.request(method_str, path, body, headers)
        else:
            raise ValueError(f"Invalid HTTP method for Adora API: {method_str}")
    else:
        # Olo and Toast support GET, POST, PUT
        if method_str in ["GET", "POST", "PUT"]:
            conn.request(method_str, path, body, headers)
        else:
            raise ValueError(
                f"Invalid HTTP method for {provider.upper()} API: {method_str}"
            )

    return conn.getresponse()


def connect_order_hub(
    provider: ApiProvider,
    http_method: Union[HttpMethod, str],
    bearer_token: Any,  # OloAccessToken, AdoraAccessToken, or ToastAccessToken
    api_function: str,
    query_params: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    payload: Optional[Union[Dict[str, Any], str]] = None,
    store_id: Optional[str] = None,  # Required for Toast API
    qa_store: bool = False,  # Required for Adora API
    general_api_endpoint: Optional[str] = None,  # Optional custom API endpoint
) -> GenericHubResponse:
    """
    Unified function to connect to different order hub APIs (Olo, Adora, Toast).

    Args:
        provider: The API provider (olo, adora, or toast)
        http_method: The HTTP method to use
        bearer_token: The access token for the specific API
        api_function: The API endpoint to call
        query_params: Optional query parameters
        extra_headers: Optional additional headers
        payload: Optional request payload
        store_id: Store ID (required for Toast API)
        qa_store: Whether to use QA environment (for Adora API)
        general_api_endpoint: Optional custom API endpoint

    Returns:
        GenericHubResponse: The API response

    Raises:
        ValueError: If the provider is invalid or required parameters are missing
        Exception: If the API request fails
    """
    logger.debug(
        f"[OrderingUtils.connect_order_hub] Calling {provider.upper()} API: {http_method} {api_function} | "
        f"General Endpoint: {general_api_endpoint} | "
        f"Query Params: {query_params} | "
        f"Extra Headers: {extra_headers} | "
        f"Payload: {payload}"
    )

    # Build base URL and path
    base_url, path_prefix = _build_base_url(provider, qa_store, general_api_endpoint)
    path = path_prefix + api_function

    # Build headers
    headers = _build_headers(provider, bearer_token, store_id, extra_headers)

    # Prepare payload
    request_body = ""
    if payload is not None:
        if isinstance(payload, dict):
            request_body = json.dumps(payload)
        else:
            request_body = str(payload)

    # Construct the full URL with query parameters
    if query_params:
        path += "?" + urllib.parse.urlencode(query_params)

    # Convert http_method to string for comparison
    if isinstance(http_method, HttpMethod):
        method_str = http_method.value
    elif isinstance(http_method, str):
        method_str = http_method.upper()
    else:
        # Handle case where http_method might be another type
        raise ValueError(f"Invalid HTTP method: {http_method}")

    try:
        conn = http.client.HTTPSConnection(base_url, timeout=30)

        # Make the request
        response = _make_request(
            conn, provider, method_str, path, request_body, headers
        )
        response_data = response.read().decode("utf-8")

        # Handle non-200 responses differently based on provider
        if provider == ApiProvider.ADORA:
            # Adora allows non-200 responses (like 404 for customer not found)
            pass
        elif provider == ApiProvider.TOAST:
            # Toast requires 200 status or 404 status
            if response.status != 200 and response.status != 404:
                raise Exception(
                    f"Error: {response.status} - {response.reason} - {response_data}"
                )
        else:
            # Olo require 200 status
            if response.status != 200:
                raise Exception(
                    f"Error: {response.status} - {response.reason} - {response_data}"
                )

        hub_response = GenericHubResponse(
            status=response.status,
            reason=response.reason,
            decoded_body=response_data,
        )

        logger.debug(
            f"[OrderingUtils.connect_order_hub] {provider.upper()} Response: {hub_response}"
        )
        return hub_response

    except Exception as e:
        raise Exception(
            f"[OrderingUtils.connect_order_hub] Error while calling {method_str} {api_function} for {provider.upper()}: {str(e)}"
        ) from e
    finally:
        conn_var = locals().get("conn")
        if conn_var:
            conn_var.close()
