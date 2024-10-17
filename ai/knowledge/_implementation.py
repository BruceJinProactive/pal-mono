from phi.knowledge.base import AssistantKnowledge
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.vectordb.pgvector.pgvector2 import PgVector2

from ai.llm import get_embedder
from db.session import db_url


def get_knowledge(account_name: str) -> AssistantKnowledge:
    knowledge_table_name = f"{account_name}_knowledge"
    get_knowledge = CombinedKnowledgeBase(
        sources=[],
        vector_db=PgVector2(
            db_url=db_url,
            collection=knowledge_table_name,
            embedder=get_embedder(),
        ),
        # 2 references are added to the prompt
        num_documents=2,
    )

    return get_knowledge


def index_data_from_shopify() -> int:
    # TODO: Implement the actual indexing logic here
    return 0
