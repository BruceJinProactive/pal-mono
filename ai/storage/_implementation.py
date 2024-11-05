from phi.storage.agent.base import AgentStorage
from phi.storage.agent.postgres import PgAgentStorage

from db.session import db_url


def get_storage(account_name: str) -> AgentStorage:
    storage_table_name = f"{account_name}_storage"
    storage = PgAgentStorage(
        db_url=db_url,
        table_name=storage_table_name,
    )

    return storage
