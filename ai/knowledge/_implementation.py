from phi.knowledge.agent import AgentKnowledge
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.vectordb.pgvector.pgvector2 import PgVector2

from ai.model import get_embedder
from db.session import db_url


def get_knowledge(account_name: str) -> AgentKnowledge:
    knowledge_table_name = f"{account_name}_knowledge"
    knowledge = CombinedKnowledgeBase(
        sources=[],
        vector_db=PgVector2(
            db_url=db_url,
            collection=knowledge_table_name,
            embedder=get_embedder(),
        ),
        # 2 references are added to the prompt
        num_documents=10,
    )

    return knowledge
