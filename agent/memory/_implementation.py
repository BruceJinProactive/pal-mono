import time
from typing import Dict, Tuple

from ddtrace.llmobs.decorators import task
from mem0 import AsyncMemoryClient

from utils.log import logger

# Simple global cache with TTL - using built-in dict
_memory_cache: Dict[str, Tuple[str, float]] = {}
_CACHE_MAXSIZE = 1000
_CACHE_TTL = 300  # 5 minutes


def _is_cache_valid(timestamp: float) -> bool:
    """Check if cache entry is still valid."""
    return time.time() - timestamp < _CACHE_TTL


def _cleanup_cache() -> None:
    """Remove expired entries and enforce size limit."""
    current_time = time.time()

    # Remove expired entries
    expired_keys = [
        key
        for key, (_, timestamp) in _memory_cache.items()
        if current_time - timestamp >= _CACHE_TTL
    ]
    for key in expired_keys:
        del _memory_cache[key]

    # Enforce size limit with LRU eviction
    if len(_memory_cache) > _CACHE_MAXSIZE:
        # Sort by timestamp (oldest first) and remove oldest entries
        sorted_items = sorted(_memory_cache.items(), key=lambda x: x[1][1])
        entries_to_remove = len(_memory_cache) - _CACHE_MAXSIZE + (_CACHE_MAXSIZE // 4)
        for key, _ in sorted_items[:entries_to_remove]:
            del _memory_cache[key]
        logger.debug(f"Cache cleanup: removed {entries_to_remove} entries")


def _get_cached_memory(user_id: str) -> str | None:
    """Get cached memory if valid."""
    if user_id in _memory_cache:
        value, timestamp = _memory_cache[user_id]
        if _is_cache_valid(timestamp):
            logger.debug(f"Cache hit for user {user_id}")
            return value
        else:
            del _memory_cache[user_id]
    return None


def _cache_memory(user_id: str, value: str) -> None:
    """Cache memory value with current timestamp."""
    _memory_cache[user_id] = (value, time.time())
    _cleanup_cache()


def _invalidate_memory_cache(user_id: str) -> None:
    """Invalidate cache for specific user."""
    if user_id in _memory_cache:
        del _memory_cache[user_id]
        logger.debug(f"Invalidated cache for user {user_id}")


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

    # Invalidate cache since memory was updated
    _invalidate_memory_cache(user_id)
    logger.debug(f"Successfully added memory for user {user_id}")


@task
async def get_all_memories(user_id: str) -> str:
    """
    Get all memories about a user. The memories are limited to the user's personal
    preferences and some of their personal information.
    Uses built-in dict cache with 5-minute TTL and LRU eviction (maxsize=1000).
    """
    # Check cache first
    cached_result = _get_cached_memory(user_id)
    if cached_result is not None:
        return cached_result

    # Cache miss - fetch from mem0
    start_time = time.perf_counter()
    client = AsyncMemoryClient()
    memories = await client.get_all(user_id=user_id)
    memories_string = ", ".join([item["memory"] for item in memories])
    elapsed_time = time.perf_counter() - start_time

    # Cache the result
    _cache_memory(user_id, memories_string)

    logger.debug(
        f"Cache miss for user {user_id} - fetched and cached memories ({elapsed_time:.4f}s): {memories_string}"
    )
    return memories_string
