from phi.storage.agent.base import AgentStorage

from . import _implementation


def get_storage(account_name: str) -> AgentStorage:
    """
    Creates and returns an AgentStorage instance for the specified account.

    This function sets up a storage system for the given account by creating a
    PgAgentStorage instance. The storage is configured to use a PostgreSQL
    database table for storing and retrieving agent-related data. The storage
    table name is derived from the account name.

    Args:
        account_name (str): The name of the account for which the storage is being created.

    Returns:
        AgentStorage: An instance of AgentStorage configured with the specified storage table.
    """
    return _implementation.get_storage(account_name)


def get_user_id_by_conversation_id(
    account_name: str, conversation_id: str
) -> str | None:
    """
    Retrieves a user ID associated with the specified conversation ID.

    This function queries the storage system to find the user ID associated
    with a given conversation ID within the specified account's context.

    Args:
        account_name (str): The name of the account to query.
        conversation_id (str): The ID of the conversation to look up.

    Returns:
        str | None: The associated user ID if found, None otherwise.
    """
    return _implementation.get_user_id_by_conversation_id(account_name, conversation_id)
