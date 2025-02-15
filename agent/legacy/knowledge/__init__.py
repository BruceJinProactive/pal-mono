from typing import Any

from agno.document.base import Document
from agno.knowledge.agent import AgentKnowledge

from . import _implementation


def get_knowledge(
    account_name: str, agent_raw_config: dict[str, Any] | None = None
) -> AgentKnowledge:
    """
    Creates and returns an AgentKnowledge instance for the specified account.

    This function sets up a knowledge base for the given account by creating a
    CombinedKnowledgeBase instance. The knowledge base is configured to use a
    PostgreSQL vector database for storing and retrieving knowledge vectors.
    The knowledge table name is derived from the account name.

    Args:
        account_name (str): The name of the account for which the knowledge base is being created.
        agent_raw_config (dict[str, Any] | None): The raw configuration for the agent. Defaults to None.

    Returns:
        AgentKnowledge: An instance of AgentKnowledge configured with the specified knowledge base.
    """
    return _implementation.get_knowledge(account_name, agent_raw_config)


def process_pdf(upload_file: Any) -> list[Document]:
    """
    Process a PDF file and return a list of documents.

    Args:
        upload_file (Any): The uploaded file.

    Returns:
        list[Document]: A list of Document objects created from the PDF file.
    """
    return _implementation.process_pdf(upload_file)


def create_document(content: str, name: str) -> Document:
    """
    Create a Document object from the provided text content and name.

    Args:
        content (str): The text content for the document.
        name (str): The name of the document.

    Returns:
        Document: A Document object.
    """

    return _implementation.create_document(content, name)
