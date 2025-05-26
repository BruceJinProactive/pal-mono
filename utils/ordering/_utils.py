import asyncio
import json
import re
import textwrap
from typing import TypeVar, Union

from ddtrace.llmobs import LLMObs
from pydantic import BaseModel, ValidationError

from agent.tool.internal.query_messages_tool import QueryMessagesTool
from utils.log import logger
from utils.ordering._llm import llm_call
from utils.ordering._query_engine import BaseQueryEngine
from utils.ordering.classes import SubQueries

T = TypeVar("T", bound=BaseModel)
S = TypeVar("S", bound=SubQueries)

VALID_PHONE_PATTERN = r"^\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})$"
VALID_EMAIL_PATTERN = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
VALID_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


# TODO: Do not pass latest_user_message as an argument. It is not needed.
def get_chat_history(
    query_messages_tool: QueryMessagesTool, latest_user_message: str
) -> str:
    """
    Retrieves the chat history from the query messages tool.

    Args:
        latest_user_message (str): The latest user message to include in the chat history.

    Returns:
        str: A string representing the entire chat history.
    """
    # TODO: The query_messages function returns error messages rather than raising exceptions. There is no generic way to verify the validity of the returned chat_history.
    chat_history: str = query_messages_tool.query_messages(latest_user_message)  # type: ignore

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
        reasoning=False,
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
            reasoning=False,
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
