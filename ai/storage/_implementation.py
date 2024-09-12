from phi.storage.assistant.base import AssistantStorage
from phi.storage.assistant.postgres import PgAssistantStorage

from db.session import db_url


def get_storage(account_name: str) -> AssistantStorage:
    storage_table_name = f"{account_name}_storage"
    storage = PgAssistantStorage(
        db_url=db_url,
        table_name=storage_table_name,
    )

    return storage
