from os import getenv
from typing import List, Optional

from openai import OpenAI
from phi.memory.memory import Memory

from ai.llm import _settings
from ai.memory import get_memory
from ai.tools.ordering_tools.classes import (
    Consumer,
    GenericCoupon,
    GenericDeliveryAddress,
    LLMCartInfo,
    LLMFulfillmentStrategy,
    LLMOrder,
)

openai_client = OpenAI(api_key=getenv("OPENAI_API_KEY"))
openai_model = _settings.ai_settings.gpt_4o_2024_08_06


def get_cart_info(chat_history: List[str]) -> Optional[LLMCartInfo]:
    """Extracts the cart information from the chat history.

    Args:
        chat_history (str): The chat history to extract the cart information from.

    Returns:
        Optional[LLMCartInfo]: The parsed cart information.
    """
    response = openai_client.beta.chat.completions.parse(
        model=openai_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "Your role is to process the chat history between a user and an assistant. You will extract the relevant order information into the desired format. You will be provided with the chat history to process.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": f"{chat_history}"}],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=LLMCartInfo,
    )

    return response.choices[0].message.parsed


def get_consumer_info(chat_history: List[str], memories: str) -> Optional[Consumer]:
    """Extracts the consumer information from the chat history.

    Args:
        chat_history (str): The chat history to extract the consumer information from.

    Returns:
        Optional[Consumer]: The parsed consumer information.
    """
    response = openai_client.beta.chat.completions.parse(
        model=openai_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """Your role is to process the chat history between a user and an assistant.
                        You will extract the relevant customer information into the desired format.
                        You will be provided with the chat history to process.
                        The phone number, if provided, MUST match the format (XXX)XXX-XXXX.
                        If the customer information is not present, output "N/A" for the missing fields.
                        """,
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{chat_history}"},
                    {"type": "text", "text": f"{memories}"},
                ],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=Consumer,
    )

    return response.choices[0].message.parsed


def get_consumer_memory(account_name: str) -> Optional[List[Memory]]:
    """Get the list of memories for the given account name.

    Args:
        account_name (str): The account name to get the memory for.

    Returns:
        Memory: The list of memories object.
    """
    memory = get_memory(account_name)
    memory.load_memory()
    memories = memory.memories
    return memories


def get_delivery_address(chat_history: list[str]) -> GenericDeliveryAddress | None:
    """Extracts the delivery address from the chat history.

    Args:
        chat_history (str): The chat history to extract the delivery address from.

    Returns:
        GenericDeliveryAddress | None: The parsed delivery address. If no delivery address is found, return "N/A".
    """
    response = openai_client.beta.chat.completions.parse(
        model=openai_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """Your role is to process the chat history between a user and an assistant.
                        You will be provided with the chat history to process.
                        You will extract the relevant delivery address information.
                        For the state field, if the user provides an abbreviation, output the full state name.
                        For example, if the user entered "CA", output "California".
                        If any field is missing, output "N/A" for that field.
                        If the user did not provide a delivery address, output "N/A" for all fields.
                        """,
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": f"{chat_history}"}],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=GenericDeliveryAddress,
    )

    return response.choices[0].message.parsed


def get_fulfillment_strategy(chat_history: list[str]) -> LLMFulfillmentStrategy | None:
    """Extracts the fulfillment strategy from the chat history.

    Args:
        chat_history (str): The chat history to extract the fulfillment strategy from.

    Returns:
        LLMFulfillmentStrategy | None: The parsed fulfillment strategy. If no fulfillment strategy is found, return "N/A".
    """
    response = openai_client.beta.chat.completions.parse(
        model=openai_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """Your role is to process the chat history between a user and an assistant.
                        You will be provided with the chat history to process.
                        You will extract the relevant fulfillment strategy.
                        The possible options are "delivery", "pickup", "dine-in", or "N/A" if no strategy is specified.
                        """,
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": f"{chat_history}"}],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=LLMFulfillmentStrategy,
    )

    return response.choices[0].message.parsed


def get_generic_coupon_info(chat_history: list[str]) -> Optional[GenericCoupon]:
    """Extracts the coupon information from the chat history.

    Args:
        chat_history (str): The chat history to extract the coupon information from.

    Returns:
        Optional[GenericCoupon]: The parsed coupon information. If no coupon information is found, return "N/A".
    """
    response = openai_client.beta.chat.completions.parse(
        model=openai_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": """Your role is to process the chat history between a user and an assistant.
                        You will be provided with the chat history to process.
                        You will extract the relevant coupon information, if the user used a coupon.
                        A user can only use one coupon per order, so extract the most recent coupon used.
                        If there is no coupon used, output "N/A" in the coupon field.
                        """,
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": f"{chat_history}"}],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=GenericCoupon,
    )

    return response.choices[0].message.parsed


# This function is currently not used.
def get_order_id(validated_order_res: str) -> Optional[LLMOrder]:
    """Extracts the order ID from the validated order response.

    Args:
        validated_order_res (str): The validated order response to extract the order ID from.

    Returns:
        Optional[LLMOrder]: The parsed order ID.
    """
    response = openai_client.beta.chat.completions.parse(
        model=openai_model,
        messages=[
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "Your role is to process the validated order message string to extract the order ID. You will be provided with the validated order message string to process.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": f"{validated_order_res}"}],
            },
        ],
        temperature=0,
        max_tokens=2048,
        response_format=LLMOrder,
    )

    return response.choices[0].message.parsed
