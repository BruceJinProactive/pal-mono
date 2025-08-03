import time
from typing import Dict, Tuple

from ddtrace.llmobs.decorators import task
from mem0 import AsyncMemoryClient

from utils.log import logger

# Simple cache: user_id -> (memories_string, timestamp)
_cache: Dict[str, Tuple[str, float]] = {}
_TTL = 300  # 5 minutes


def _get_cached_memories(user_id: str) -> str | None:
    """Get cached memories if still valid."""
    if user_id not in _cache:
        return None

    memories, timestamp = _cache[user_id]
    if time.time() - timestamp > _TTL:
        del _cache[user_id]  # Expired
        return None

    logger.debug(f"Cache hit for user {user_id}")
    return memories


def _set_cached_memories(user_id: str, memories: str) -> None:
    """Cache memories with current timestamp."""
    _cache[user_id] = (memories, time.time())
    logger.debug(f"Cached memories for user {user_id}")


def _clear_user_cache(user_id: str) -> None:
    """Remove cached memories for user."""
    if user_id in _cache:
        del _cache[user_id]
        logger.debug(f"Cleared cache for user {user_id}")


@task(name="Memory Update")
async def update_memory(
    user_id: str,
    content: str,
    role: str = "user",
    session_id: str | None = None,
) -> None:
    client = AsyncMemoryClient()
    logger.debug(f"Updating memory for user {user_id} with content: {content}")
    await client.add(
        messages=[
            {
                "role": role,
                "content": content,
            }
        ],
        user_id=user_id,
        session_id=session_id,
        model="gpt-4o-mini",
    )

    # Clear cache since memory was updated
    _clear_user_cache(user_id)
    logger.debug(f"Successfully added memory for user {user_id}")


@task
async def get_all_memories(user_id: str) -> str:
    """
    Get all memories about a user. The memories are limited to the user's personal
    preferences and some of their personal information.
    Uses simple 5-minute TTL cache.
    """
    # Check cache first
    cached_memories = _get_cached_memories(user_id)
    if cached_memories is not None:
        return cached_memories

    # Cache miss - fetch from mem0
    start_time = time.perf_counter()
    client = AsyncMemoryClient()
    memories = await client.get_all(user_id=user_id)
    memories_string = ", ".join([item["memory"] for item in memories])
    elapsed_time = time.perf_counter() - start_time

    # Cache the result
    _set_cached_memories(user_id, memories_string)

    logger.debug(
        f"Cache miss for user {user_id} - fetched memories ({elapsed_time:.4f}s): {memories_string}"
    )
    return memories_string
