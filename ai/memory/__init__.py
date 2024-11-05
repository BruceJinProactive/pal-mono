from phi.memory.agent import AgentMemory

from . import _implementation


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
