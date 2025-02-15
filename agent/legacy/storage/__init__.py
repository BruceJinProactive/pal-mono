from agno.storage.agent.base import AgentStorage

from . import _implementation


def get_storage(account_name: str) -> AgentStorage:
    """
    Creates and returns an AgentStorage instance for the specified account.

    This function sets up a storage system for the given account by creating a
    PostgresAgentStorage instance. The storage is configured to use a PostgreSQL
    database table for storing and retrieving agent-related data. The storage
    table name is derived from the account name.

    Args:
        account_name (str): The name of the account for which the storage is being created.

    Returns:
        AgentStorage: An instance of AgentStorage configured with the specified storage table.
    """
    return _implementation.get_storage(account_name)
