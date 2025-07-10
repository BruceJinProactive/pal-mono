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
        prompt = f"""
You are an assistant that generates short, natural filler phrases to use during conversation pauses based on the complexity of a user's query.

Instructions:

- For COMPLEX queries (keywords like “recommend”, “menu”, “price”, “compare”, “when open”, “hours”), generate a natural filler phrase between 8 and 15 words.
- For SIMPLE queries (greetings, yes/no questions, thanks), generate a short filler phrase between 1 and 5 words.
- Output ONLY the filler phrase—no complete sentences, no punctuation at the end, and no explanations.
- Be conversational and natural.

Examples:

User query: "What restaurant do you recommend?"
Filler words: Let me find some great options for you

User query: "Hello"
Filler words: Hi there

User query: "So when the store is open,"
Filler words: Let me check the store hours for you

User query: "{user_message}"
Filler words:
"""

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

            if content:
                # Yield the chunk when content is present
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
