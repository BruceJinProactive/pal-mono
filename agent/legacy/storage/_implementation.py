from agno.storage.agent.base import AgentStorage
from agno.storage.agent.postgres import PostgresAgentStorage

import db


def get_storage(account_name: str) -> AgentStorage:
    storage_table_name = f"{account_name}_storage_agno"
    storage = PostgresAgentStorage(
        db_url=db.db_url,
        table_name=storage_table_name,
    )

    return storage
