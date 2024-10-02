from phi.memory.assistant import AssistantMemory
from phi.memory.db.postgres import PgMemoryDb

from db.session import db_url


def get_memory(account_name: str) -> AssistantMemory:
    memory_table_name = f"{account_name}_memory"
    memory = AssistantMemory(
        db=PgMemoryDb(
            db_url=db_url,
            table_name=memory_table_name,
        ),
    )
    return memory
