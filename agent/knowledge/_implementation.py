from phi.knowledge.agent import AgentKnowledge
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.vectordb.pgvector.pgvector2 import PgVector2

import db
from agent.config import KnowledgeConfig
from agent.model import get_embedder


def get_knowledge(config: KnowledgeConfig) -> AgentKnowledge:
    knowledge_table_name = f"{config.identifier}_knowledge"
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
