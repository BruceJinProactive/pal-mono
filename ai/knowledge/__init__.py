from phi.knowledge.agent import AgentKnowledge

from . import _implementation


def get_knowledge(account_name: str) -> AgentKnowledge:
    """
    Creates and returns an AgentKnowledge instance for the specified account.

    This function sets up a knowledge base for the given account by creating a
    CombinedKnowledgeBase instance. The knowledge base is configured to use a
    PostgreSQL vector database for storing and retrieving knowledge vectors.
    The knowledge table name is derived from the account name.

    Args:
        account_name (str): The name of the account for which the knowledge base is being created.

    Returns:
        AgentKnowledge: An instance of AgentKnowledge configured with the specified knowledge base.
    """
    return _implementation.get_knowledge(account_name)
