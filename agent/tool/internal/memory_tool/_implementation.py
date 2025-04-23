import asyncio

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs.decorators import tool

from agent.memory import get_all_memories


class MemoryTool(Toolkit):
    def __init__(self, user_id: str):
        super().__init__(name="memory_tool")
        self.user_id = user_id
        self.register(self.get_all_memories)

    @tool
    def get_all_memories(self) -> str:
        """
        Retrieve all memories (from past conversations) about the user.
        The memories contain information about the user's preferences, their personal information.
        Use this tool only when memory about the user can be relevant to the current user's query.

        Returns:
            str: A string containing all memories about the user.
        """
        memories_string = asyncio.run(get_all_memories(user_id=self.user_id))  # type: ignore
        return memories_string
