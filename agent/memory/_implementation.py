import time

from ddtrace.llmobs.decorators import task
from mem0 import AsyncMemoryClient

from utils.log import logger
from utils.sys import log_sys_info


@task
async def update_memory(
    user_id: str,
    content: str,
    role: str = "user",
    session_id: str | None = None,
) -> None:
    client = AsyncMemoryClient()
    logger.debug(f"Updating memory for user {user_id} with content: {content}")
    log_sys_info("update_memory")
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


@task
async def get_all_memories(user_id: str) -> str:
    """
    Get all memories about a user. The memories are limited to the user's personal
    preferences and some of their personal information.
    """
    start_time = time.perf_counter()
    client = AsyncMemoryClient()
    memories = await client.get_all(user_id=user_id)
    memories_string = ", ".join([item["memory"] for item in memories])
    logger.debug(f"All memories for user {user_id}: {memories_string}")
    logger.debug(f"Get all memories took: {time.perf_counter() - start_time:.4f}s")
    return memories_string
