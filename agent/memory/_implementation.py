from mem0 import AsyncMemoryClient


async def update_memory(
    user_id: str, content: str, role: str = "user", session_id: str | None = None
) -> None:
    client = AsyncMemoryClient()
    await client.add(
        messages=[
            {
                "role": role,
                "content": content,
            }
        ],
        user_id=user_id,
        run_id=session_id,
    )


async def get_memory_context(user_id: str) -> str:
    client = AsyncMemoryClient()

    # Perform the search with specified fields
    memories = await client.get_all(
        user_id=user_id,
        fields=["memory"],
    )
    memories = [item["memory"] for item in memories]
    memories_string = ", ".join(memories)

    return memories_string
