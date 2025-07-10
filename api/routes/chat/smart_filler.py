import asyncio
import datetime
import os
import random
import uuid
from typing import AsyncIterator

import openai
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta

from utils.log import logger


async def get_smart_filler_stream(
    user_message: str,
    static_mode: bool = False,
) -> AsyncIterator[ChatCompletionChunk]:
    """
    Generate real-time streaming filler chunks based on user query complexity.

    Args:
        user_message: The user's original message
        static_mode: If True, use pre-defined static fillers; if False, use OpenAI

    Yields:
        Streaming chunks with filler content (static or context-aware from OpenAI)
    """
    if not user_message or not user_message.strip():
        logger.debug("Empty user message, skipping filler")
        return

    if static_mode:
        logger.debug("[SmartFiller] Starting streaming in static mode")
        async for chunk in _get_static_mode_stream(user_message):
            yield chunk
        return

    model = "gpt-3.5-turbo"
    try:
        logger.debug("[SmartFiller] Starting streaming smart filler generation")
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
            temperature=0.3,
            max_tokens=40,
            timeout=1.5,
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


async def _get_static_mode_stream(
    user_message: str,
) -> AsyncIterator[ChatCompletionChunk]:
    """
    Generate real-time streaming static mode chunks with pre-defined words.

    Args:
        user_message: The user's original message

    Yields:
        Streaming chunks with pre-defined filler content
    """
    # Pre-defined filler phrases - much faster than OpenAI API calls
    simple_fillers = [
        "One moment",
        "Just a sec",
        "Let me check",
        "Hold on",
        "Give me a moment",
        "Please wait",
        "Looking into it",
        "Checking now",
    ]

    complex_fillers = [
        "Let me find that information for you",
        "I'm looking up the details",
        "Let me check what I can find",
        "Searching for the best options",
        "Let me gather that information",
        "I'll find what you need",
        "Let me see what's available",
        "Looking for the right details",
    ]

    # Simple heuristic to determine if query is complex
    # Check for keywords that typically indicate more complex requests
    complex_keywords = [
        "recommend",
        "suggestion",
        "compare",
        "when",
        "where",
        "how",
        "what",
        "why",
        "which",
        "menu",
        "price",
        "cost",
        "open",
        "hours",
        "schedule",
        "available",
        "options",
        "best",
        "better",
        "different",
        "alternatives",
    ]

    user_lower = user_message.lower()
    is_complex = any(keyword in user_lower for keyword in complex_keywords)

    # Select appropriate filler based on complexity
    if is_complex:
        selected_filler = random.choice(complex_fillers)
    else:
        selected_filler = random.choice(simple_fillers)

    logger.debug(
        f"[StaticMode] Selected filler: '{selected_filler}' for query: '{user_message[:50]}...'"
    )

    try:
        model = "static-filler"
        chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
        created_timestamp = int(
            datetime.datetime.now(datetime.timezone.utc).timestamp()
        )

        # Split the filler into words and stream them
        words = selected_filler.split()

        for i, word in enumerate(words):
            # Add space before word except for the first word
            content = word if i == 0 else f" {word}"

            # Create and yield chunk
            yield ChatCompletionChunk(
                id=chunk_id,
                object="chat.completion.chunk",
                created=created_timestamp,
                model=model,
                choices=[
                    Choice(
                        index=i,
                        delta=ChoiceDelta(role="assistant", content=content),
                        finish_reason=None,
                    )
                ],
            )

            logger.debug(f"[StaticMode] Streamed chunk: '{content}'")

            # Small delay to simulate natural speech pattern
            await asyncio.sleep(0.05)  # 50ms delay between words

        logger.debug("[StaticMode] Completed streaming static filler")

    except Exception as e:
        logger.warning(f"[StaticMode] Error in streaming: {e}")
        # Return a simple fallback filler if something goes wrong
        fallback_content = "One moment"
        yield ChatCompletionChunk(
            id=f"chatcmpl-{uuid.uuid4().hex}",
            object="chat.completion.chunk",
            created=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
            model="static-filler",
            choices=[
                Choice(
                    index=0,
                    delta=ChoiceDelta(role="assistant", content=fallback_content),
                    finish_reason=None,
                )
            ],
        )
        logger.debug(f"[StaticMode] Used fallback: '{fallback_content}'")
