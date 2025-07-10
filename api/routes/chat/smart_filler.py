import datetime
import os
import uuid
from typing import AsyncIterator

import openai
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta

from utils.log import logger


async def get_smart_filler_stream(
    user_message: str,
) -> AsyncIterator[ChatCompletionChunk]:
    """
    Generate real-time streaming smart filler chunks based on user query complexity.

    Args:
        user_message: The user's original message

    Yields:
        Streaming chunks with context-aware filler content as it arrives from OpenAI
    """
    if not user_message or not user_message.strip():
        logger.debug("Empty user message, skipping smart filler")
        return

    model = "gpt-3.5-turbo"
    try:
        logger.info("[SmartFiller] Starting streaming smart filler generation")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        client = openai.AsyncOpenAI(api_key=api_key)

        # Create a fast, focused prompt for context-aware filler
        prompt = f"""User query: "{user_message}"

Generate appropriate filler words based on query complexity:

COMPLEX QUERIES (need longer filler, 8-15 words):
- Recommendations ("what restaurant", "recommend", "suggest")
- Menu details ("menu", "what's available", "options")
- Prices ("price", "cost", "how much")
- Comparisons ("compare", "difference", "better")
- Location/hours ("where", "when open", "hours")

SIMPLE QUERIES (need short filler, 1-5 words):
- Greetings ("hello", "hi", "hey")
- Yes/no questions ("is", "can", "do you")
- Thanks ("thank", "thanks")

Generate ONLY the filler words, no explanation. Be natural and conversational.

Examples:
- "What restaurant do you recommend?" → "Let me find some great options for you..."
- "What's the menu like?" → "Let me check what's available..."
- "How much does it cost?" → "Let me look up the pricing..."
- "Hello" → "Hi there!"
- "Thank you" → "You're welcome!"

Filler words:"""

        # Use streaming with optimized settings for speed
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,  # Lower temperature for more consistent, faster responses
            max_tokens=40,  # Limit tokens for faster generation
            timeout=1.5,  # Short timeout for speed
            stream=True,
        )

        chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_timestamp = int(
            datetime.datetime.now(datetime.timezone.utc).timestamp()
        )

        # Stream chunks as they arrive with proper error handling
        index = 0
        async for chunk in response:
            if not chunk.choices:
                continue

            choice = chunk.choices[0]

            content = None

            if hasattr(choice, "delta") and choice.delta:
                content = getattr(choice.delta, "content", None)

            # Always yield the chunk (even without content for proper stream termination)
            yield ChatCompletionChunk(
                id=chunk_id,
                object="chat.completion.chunk",
                created=created_timestamp,
                model=model,
                choices=[
                    Choice(
                        index=index,
                        delta=ChoiceDelta(role="assistant", content=content),
                        finish_reason=None,
                    )
                ],
            )
            if content:
                logger.debug(f"[SmartFiller] Streamed chunk: '{content}'")
            index += 1

        logger.debug("[SmartFiller] Completed streaming smart filler")

    except Exception as e:
        logger.warning(f"[SmartFiller] Error in streaming: {e}")
        # Return a simple fallback filler if OpenAI fails
        fallback_content = "One moment"
        yield ChatCompletionChunk(
            id=f"chatcmpl-{uuid.uuid4().hex}",
            object="chat.completion.chunk",
            created=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
            model=model,
            choices=[
                Choice(
                    index=0,
                    delta=ChoiceDelta(role="assistant", content=fallback_content),
                    finish_reason=None,
                )
            ],
        )
        logger.debug(f"[SmartFiller] Used fallback: '{fallback_content}'")
