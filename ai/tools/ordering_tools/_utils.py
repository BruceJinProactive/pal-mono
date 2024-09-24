from os import getenv
from typing import Optional

from openai import OpenAI

from ai.llm import _settings
from ai.tools.ordering_tools.classes import LLMCartInfo, LLMOrder

openai_client = OpenAI(api_key=getenv("OPENAI_API_KEY"))
openai_model = _settings.ai_settings.gpt_4o_2024_08_06


def get_cart_info(chat_history: str) -> Optional[LLMCartInfo]:
    """Extracts the cart information from the chat history.

    Args:
        chat_history (str): The chat history to extract the cart information from.

    Returns:
        Optional[LLMCartInfo]: The parsed cart information.
    """
    response = openai_client.chat.completions.parse(
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


def get_order_id(validated_order_res: str) -> Optional[LLMOrder]:
    """Extracts the order ID from the validated order response.

    Args:
        validated_order_res (str): The validated order response to extract the order ID from.

    Returns:
        Optional[LLMOrder]: The parsed order ID.
    """
    response = openai_client.chat.completions.parse(
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
