from typing import Any

from agno.memory.agent import AgentMemory
from agno.memory.classifier import MemoryClassifier
from agno.memory.db.postgres import PgMemoryDb
from agno.memory.manager import MemoryManager
from agno.memory.memory import Memory
from agno.models.base import Model
from agno.models.message import Message

import db
from agent.model import ModelName, get_model
from utils.log import logger

DEFAULT_NUM_HISTORY_RESPONSES = 10


def add_memory(memory: AgentMemory, new_memory_input: str) -> None:
    """
    Add the specified memory to the agent's memory list and the memory database.

    Parameters:
        memory (AgentMemory): The `AgentMemory` object to be updated.
        new_memory_input (Str): The memory to be added.

    Returns:
        None
    """
    new_memory = Memory(memory=new_memory_input)
    if memory.manager:
        memory.manager.add_memory(new_memory.memory)


def clear_memory(account_name: str, user_id: str) -> None:
    """
    Clear all memories from the agent's memory list and the memory database.

    Parameters:
        account_name (str): The name of the account.
        user_id (str): The user ID.

    Returns:
        None
    """
    memory = get_memory(account_name)
    set_memory_manager(memory, user_id)
    memory.load_user_memories()
    if memory.manager is None:
        memory.manager = MemoryManager(user_id=user_id, db=memory.db)
    memory.manager.clear_memory()


def delete_memory(memory: AgentMemory, memory_id: str) -> None:
    """
    Delete the specified memory from both the agent's memory list and the memory database.
    Parameters:
        memory (AgentMemory): The `AgentMemory` object to be updated.
        memory_id (str): The unique identifier of the memory to be removed.
    Returns:
        None
    Raises:
        ValueError: If the memory_id is invalid or not found
    """
    if memory.manager is None:
        memory.manager = MemoryManager(user_id=memory.user_id, db=memory.db)
    try:
        memory.manager.delete_memory(memory_id)
    except Exception as e:
        logger.error("[legacy.memory.delete_memory] Failed to delete memory: %s", e)


def get_history_responses(agent_raw_config: dict[str, Any]) -> int:
    """
    Get the number of history responses from the agent's raw configuration.

    Parameters:
        agent_raw_config (dict[str, Any]): The raw configuration of the agent.

    Returns:
        int: The number of history responses.

     Example:
        agent_raw_config = {
            "num_history_responses": 5
        }
        num_history_responses = get_history_responses(agent_raw_config)
    """
    num_history_responses = DEFAULT_NUM_HISTORY_RESPONSES
    if "num_history_responses" in agent_raw_config:
        value = agent_raw_config.get("num_history_responses")
        if isinstance(value, int):
            num_history_responses = value
    return num_history_responses


def get_memory(
    account_name: str, agent_raw_config: dict[str, Any] | None = None
) -> AgentMemory:
    """
    Creates and returns an AgentMemory instance for the specified account.

    Parameters:
        account_name (str): The name of the account for which the memory is being created.
        agent_raw_config (dict[str, Any]): The raw configuration (Optional) of the agent,.

    Returns:
        AgentMemory: The AgentMemory instance for the specified
    """
    memory_table_name = f"{account_name}_memory_agno"
    memory = AgentMemory(
        db=PgMemoryDb(
            db_url=db.db_url,
            table_name=memory_table_name,
        ),
        create_user_memories=True,
    )
    system_prompt_lines = None
    # Use custom system prompt lines if provided, if not use default
    if (
        agent_raw_config
        and "memory_prompt" in agent_raw_config
        and agent_raw_config["memory_prompt"]
    ):
        system_prompt_lines = agent_raw_config["memory_prompt"]
        memory.classifier = CustomMemoryClassifier(
            memory_system_prompt_lines=system_prompt_lines
        )
    return memory


def set_memory_manager(memory: AgentMemory, user_id: str) -> MemoryManager:
    """
    Set the memory manager for the agent's memory.

    Parameters:
        memory (AgentMemory): The `AgentMemory` object to be updated.
        user_id (str): The user ID.

    Returns:
        None
    """
    memory.manager = MemoryManager(user_id=user_id, db=memory.db)
    return memory.manager


class CustomMemoryClassifier(MemoryClassifier):
    memory_system_prompt_lines: list[str] = []

    def __init__(self, memory_system_prompt_lines: list[str]):
        super().__init__()
        # Use custom system prompt lines if provided, otherwise use default
        self.memory_system_prompt_lines = memory_system_prompt_lines
        # Initialize instance-specific attributes
        self.model: Model | None = None
        self.system_prompt: str | None = None

    # Overridden to utilize our model router
    def update_model(self) -> None:
        if self.model is None:
            self.model = get_model(model_name=ModelName.MEDIUM, stream=False)

    # Overridden to utilize current markdown formatting strategy
    def get_system_message(self) -> Message:
        # -*- Return a system message for classification
        system_prompt_lines = self.memory_system_prompt_lines

        if self.existing_memories and len(self.existing_memories) > 0:
            system_prompt_lines.extend(
                [
                    "\n ## Existing Memories: \n"
                    + "\n".join([f"  - {m.memory}" for m in self.existing_memories])
                ]
            )

        return Message(
            role="system",
            content="\n".join(system_prompt_lines),
        )
