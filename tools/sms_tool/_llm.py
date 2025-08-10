from typing import Optional

from tools.utils.ordering._llm import llm_call
from utils.log import logger

# System prompt for generating order summaries
ORDER_SUMMARY_SYSTEM_PROMPT = """You are a helpful assistant that summarizes order details into clear, concise summaries.
Your task is to:
1. List all ordered items with their quantities
2. Include the total amount
3. Include delivery address if provided
4. Include any special instructions

The summary should be clear, professional, and easy to understand.
Format the information in a way that's easy to read in an SMS message."""

# User prompt template for order summaries
ORDER_SUMMARY_USER_PROMPT = """Please summarize the following order details:

{chat_history}

Provide a clear summary that includes:
1. All ordered items with quantities
2. Total amount
3. Delivery address (if provided)
4. Special instructions (if any)

Format the information in a way that's easy to read in an SMS message."""


def generate_order_summary(chat_history: str) -> Optional[str]:
    """
    Generate a summary of an order using LLM.

    Args:
        chat_history (str): The conversation containing order details

    Returns:
        Optional[str]: A formatted summary of the order, or None if generation failed
    """
    try:
        response = llm_call(
            system_prompt=ORDER_SUMMARY_SYSTEM_PROMPT,
            prompt=ORDER_SUMMARY_USER_PROMPT.format(chat_history=chat_history),
            openai=False,
        )

        if not response:
            return None

        return str(response).strip()
    except Exception as e:
        logger.error(f"[generate_order_summary] Error: {e}")
        return None
