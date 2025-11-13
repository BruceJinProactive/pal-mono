import time
from typing import Dict, List, Tuple

from ddtrace.llmobs import LLMObs
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

    logger.debug(f"Successfully added memory for user {user_id}")


@task(name="Get All Memories")
async def get_all_memories(user_id: str) -> str:
    """
    Get all memories about a user. The memories are limited to the user's personal
    preferences and some of their personal information.
    Uses simple 5-minute TTL cache. Returns empty string if not cached to avoid blocking.
    """
    # Check cache first
    cached_memories = _get_cached_memories(user_id)
    if cached_memories is not None:
        LLMObs.annotate(
            tags={
                "cache_hit": True,
            }
        )
        return cached_memories

    # Cache miss - start background task to populate cache, return empty string immediately
    import asyncio

    asyncio.create_task(_fetch_and_cache_memories(user_id))
    logger.debug(f"Cache miss for user {user_id} - started background fetch")
    LLMObs.annotate(
        tags={
            "cache_hit": False,
        }
    )
    return ""


@task(name="Fetch and Cache Memories")
async def _fetch_and_cache_memories(user_id: str) -> None:
    """Background task to fetch and cache memories without blocking."""
    try:
        start_time = time.perf_counter()
        client = AsyncMemoryClient()
        memories: Dict[str, List] = await client.get_all(user_id=user_id)  # type: ignore
        memories_string = ", ".join([item["memory"] for item in memories["results"]])
        elapsed_time = time.perf_counter() - start_time

        # Cache the result
        _set_cached_memories(user_id, memories_string)
        logger.debug(
            f"Background fetch completed for user {user_id} ({elapsed_time:.4f}s): {memories_string}"
        )
    except Exception as e:
        logger.error(f"Background memory fetch failed for user {user_id}: {e}")
