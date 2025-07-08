import datetime
import os
import uuid
from typing import Tuple

import openai

from utils.log import logger


async def should_use_smart_filler(user_message: str) -> Tuple[bool, str]:
    """
    Use LLM to categorize user query and decide if filler is needed.

    Args:
        user_message: The user's original message

    Returns:
        Tuple of (should_use_filler, filler_text)
    """
    if not user_message or not user_message.strip():
        logger.debug("Empty user message, skipping smart filler")
        return False, ""

    try:
        logger.info("######## Run smart filler")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        client = openai.AsyncOpenAI(api_key=api_key)

        prompt = f"""Analyze this user query: "{user_message}"

Determine if this type of query typically requires processing time and would benefit from a filler phrase in voice conversation.

NEEDS FILLER (complex/time-consuming):
- Making orders/purchases
- Asking for recommendations
- Store hours/location queries
- Complex calculations
- Multi-step processes
- Research-heavy questions

NO FILLER NEEDED (quick/simple):
- Simple yes/no questions
- Basic greetings
- Single facts
- Quick confirmations

If filler is needed, provide a natural, contextual phrase appropriate for the query type.

Respond EXACTLY as:
YES|<filler_phrase>
or
NO

Examples:
- "I want to order a pizza" -> YES|Let me help you place that order.
- "What time do you close?" -> YES|Let me check our hours for you.
- "Can you recommend a good restaurant?" -> YES|Let me find some great options for you.
- "Hello" -> NO
- "Thanks" -> NO"""

        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=30,
            timeout=2.0,
        )

        result = (
            response.choices[0].message.content.strip()
            if response.choices[0].message.content
            else ""
        )
        logger.debug(f"Smart filler decision for '{user_message[:50]}...': {result}")

        if result.startswith("YES|"):
            parts = result.split("|", 1)
            if len(parts) == 2:
                filler_text = parts[1].strip()
                if filler_text:  # Ensure filler text is not empty
                    return True, filler_text
                else:
                    logger.warning(
                        "Empty filler text received, falling back to no filler"
                    )
                    return False, ""
            else:
                logger.warning("Invalid YES format received, falling back to no filler")
                return False, ""
        else:
            return False, ""

    except Exception as e:
        logger.warning(f"Smart filler error: {e}, using fallback")
        return False, ""


def generate_smart_filler_chunk(model: str, filler_text: str) -> dict:
    """Generate streaming chunk with filler content."""
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": filler_text},
                "finish_reason": None,
            }
        ],
    }
