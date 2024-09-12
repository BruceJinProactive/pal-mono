from phi.knowledge.base import AssistantKnowledge
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.vectordb.pgvector import PgVector2

from ai.llms import get_embedder
from db.session import db_url


def get_knowledge_base(account_name: str) -> AssistantKnowledge:
    knowledge_base_table_name = f"{account_name}_knowledge_base"
    knowledge_base = CombinedKnowledgeBase(
        sources=[],
        vector_db=PgVector2(
            db_url=db_url,
            collection=knowledge_base_table_name,
            embedder=get_embedder(),
        ),
        # 2 references are added to the prompt
        num_documents=2,
    )

    return knowledge_base
