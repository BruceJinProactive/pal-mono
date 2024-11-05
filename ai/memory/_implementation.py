from phi.memory.agent import AgentMemory
from phi.memory.db.postgres import PgMemoryDb

from db.session import db_url


def get_memory(account_name: str) -> AgentMemory:
    memory_table_name = f"{account_name}_memory"
    memory = AgentMemory(
        db=PgMemoryDb(
            db_url=db_url,
            table_name=memory_table_name,
        ),
        create_user_memories=True,
    )
    return memory
