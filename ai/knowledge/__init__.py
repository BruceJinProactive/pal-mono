from phi.knowledge.base import AssistantKnowledge

from . import _implementation


def get_knowledge(account_name: str) -> AssistantKnowledge:
    """
    Create and return an AssistantKnowledge instance for the given account.

    This function sets up a CombinedKnowledgeBase with a PgVector2 vector database
    and an embedder. The knowledge base is configured to use a specific table name
    based on the account name and includes 2 reference documents in the prompt.

    Args:
        account_name (str): The name of the account for which to create the knowledge base.

    Returns:
        AssistantKnowledge: An instance of AssistantKnowledge configured with the specified settings.
    """
    return _implementation.get_knowledge(account_name)
