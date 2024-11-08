from phi.memory.agent import AgentMemory
from phi.memory.memory import Memory

from . import _implementation


def add_memory(memory: AgentMemory, new_memory: str) -> None:
    """
    Add the specified memory to the agent's memory list and the memory database.

    Args:
        memory (AgentMemory): The `AgentMemory` object to be updated.
        new_memory (str): The memory to be added.

    Returns:
        None
    """
    return _implementation.add_memory(memory, new_memory)


def clear_memory(account_name: str, user_id: str) -> None:
    """
    Clear all memories from the agent's memory list and the memory database.

    Args:
        account_name (str): The name of the account.
        user_id (str): The user ID.

    Returns:
        None
    """
    return _implementation.clear_memory(account_name, user_id)


def delete_memory(memory: AgentMemory, removed_memory: Memory) -> None:
    """
    Delete the specified memory from both the agent's memory list and the memory database.

    Args:
        memory (AgentMemory): The `AgentMemory` object to be updated.
        removed_memory (str): The memory to be removed.

    Returns:
        None
    """
    return _implementation.delete_memory(memory, removed_memory)


def get_memory(account_name: str) -> AgentMemory:
    """
    Creates and returns an AgentMemory instance for the specified account.

    This function sets up a memory system for the given account by creating an
    AgentMemory instance. The memory is configured to use a PostgreSQL database
    table for storing and retrieving memory-related data. The memory table name
    is derived from the account name. Additionally, it enables the creation of
    user-specific memories.

    Args:
        account_name (str): The name of the account for which the memory is being created.
    Returns:
        AgentMemory: An instance of AgentMemory configured with the specified memory table.
    """
    return _implementation.get_memory(account_name)


def set_memory_manager(memory: AgentMemory, memory_id: str) -> None:
    """
    Set the memory manager for the agent's memory list and the memory database.

    Args:
        memory (AgentMemory): The `AgentMemory` object to be updated.
        memory_id (str): The memory to be added.

    Returns:
        None
    """
    return _implementation.set_memory_manager(memory, memory_id)
