from ddtrace.llmobs.decorators import task
from mem0 import AsyncMemoryClient

from utils.log import logger


def get_memory_client():
    return AsyncMemoryClient()


@task
async def update_memory(
    user_id: str,
    content: str,
    role: str = "user",
    client: AsyncMemoryClient | None = None,
) -> None:
    client = client or get_memory_client()
    logger.info(f"Updating memory for user {user_id} with content: {content}")
    await client.add(
        content,
        role=role,
        user_id=user_id,
        model="gpt-4o-mini",
    )

    logger.info(f"Successfully added memory for user {user_id}")


@task
async def get_all_memories(
    user_id: str, client: AsyncMemoryClient | None = None
) -> str:
    """
    Get all memories about a user. The memories are limited to the user's personal
    preferences and some of their personal information.
    """
    client = client or get_memory_client()
    memories = await client.get_all(user_id=user_id)
    memories_string = ", ".join([item["memory"] for item in memories])
    logger.info(f"All memories for user {user_id}: {memories_string}")
    return memories_string
