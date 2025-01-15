from phi.storage.agent.base import AgentStorage
from phi.storage.agent.postgres import PgAgentStorage
from sqlalchemy import text

import db


def get_storage(account_name: str) -> AgentStorage:
    storage_table_name = f"{account_name}_storage"
    storage = PgAgentStorage(
        db_url=db.db_url,
        table_name=storage_table_name,
    )

    return storage


def get_user_id_by_conversation_id(
    account_name: str, conversation_id: str
) -> str | None:
    """
    Retrieves the user_id associated with a given conversation_id from the storage table.

    Args:
        account_name (str): The account name to determine the storage table.
        conversation_id (str): The conversation ID to search for.

    Returns:
        Optional[str]: The associated user_id if found, else None.
    """
    # Construct the storage table name
    storage_table_name = f"{account_name}_storage"

    # Initialize PgAgentStorage with the appropriate schema if needed
    storage = PgAgentStorage(
        db_url=db.db_url,
        table_name=storage_table_name,
        schema="ai",
    )

    # Construct the fully qualified table name including schema
    full_table_name = (
        f"{storage.schema}.{storage.table_name}"
        if storage.schema
        else storage.table_name
    )

    # Use JSONB operators to efficiently query the conversation_id
    query = text(
        f"""
        SELECT memory
        FROM {full_table_name}
        WHERE memory::text LIKE '%{conversation_id}%'
        ORDER BY session_id ASC
        LIMIT 1
    """
    )

    with storage.Session() as sess:
        row = sess.execute(query).fetchone()
        return row[0]["user_id"] if row else None
