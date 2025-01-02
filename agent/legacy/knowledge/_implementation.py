from typing import Any

from phi.document.base import Document
from phi.document.reader.pdf import PDFReader
from phi.knowledge.agent import AgentKnowledge
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.vectordb.pgvector.pgvector2 import PgVector2

import db
from agent.model import get_embedder


def get_knowledge(account_name: str) -> AgentKnowledge:
    knowledge_table_name = f"{account_name}_knowledge"
    knowledge = CombinedKnowledgeBase(
        sources=[],
        vector_db=PgVector2(
            db_url=db.db_url,
            collection=knowledge_table_name,
            embedder=get_embedder(),
        ),
        # 2 references are added to the prompt
        num_documents=10,
    )

    return knowledge


def process_pdf(uploaded_file: Any) -> list[Document]:
    """
    Process a PDF file and return a list of documents.

    Args:
        uploaded_file (Any): The uploaded PDF file.

    Returns:
        list[Document]: A list of Document objects created from the PDF file.
    """

    reader = PDFReader()
    return reader.read(uploaded_file)


def create_document(content: str, name: str) -> Document:
    """
    Create a Document object from the provided text content and name.

    Args:
        content (str): The text content for the document.
        name (str): The name of the document.

    Returns:
        Document: A Document object.
    """

    return Document(content=content, name=name)
