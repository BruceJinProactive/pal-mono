from phi.memory.agent import AgentMemory
from phi.memory.db.postgres import PgMemoryDb
from phi.memory.manager import MemoryManager
from phi.memory.memory import Memory

import db


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


def delete_memory(memory: AgentMemory, removed_memory: Memory) -> None:
    """
    Delete the specified memory from both the agent's memory list and the memory database.

    Parameters:
        memory (AgentMemory): The `AgentMemory` object to be updated.
        removed_memory (Memory): The `Memory` object to be removed.

    Returns:
        None
    """

    if memory.manager is None:
        memory.manager = MemoryManager(user_id=memory.user_id, db=memory.db)

    memories = memory.memories
    if memories and removed_memory and removed_memory in memories:
        memories.remove(removed_memory)
    memory.manager.clear_memory()
    if memories:
        for memo in memories:
            memory.manager.add_memory(memo.memory)


def get_memory(account_name: str) -> AgentMemory:
    """
    Creates and returns an AgentMemory instance for the specified account.

    Parameters:
        account_name (str): The name of the account for which the memory is being created.

    Returns:
        AgentMemory: The AgentMemory instance for the specified
    """
    memory_table_name = f"{account_name}_memory"
    memory = AgentMemory(
        db=PgMemoryDb(
            db_url=db.db_url,
            table_name=memory_table_name,
        ),
        create_user_memories=True,
    )
    return memory


def set_memory_manager(memory: AgentMemory, user_id) -> None:
    """
    Set the memory manager for the agent's memory.

    Parameters:
        memory (AgentMemory): The `AgentMemory` object to be updated.
        user_id (str): The user ID.

    Returns:
        None
    """
    memory.manager = MemoryManager(user_id=user_id, db=memory.db)
    return None
