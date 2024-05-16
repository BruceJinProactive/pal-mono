from typing import Optional
from os import getenv

import logging

from phi.assistant import Assistant
from phi.llm.openai.like import OpenAILike

from ai.storage import pdf_assistant_storage
from ai.knowledge_base import pdf_knowledge_base
from phi.embedder.openai import OpenAIEmbedder
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.knowledge.pdf import PDFUrlKnowledgeBase, PDFKnowledgeBase
from phi.knowledge.website import WebsiteKnowledgeBase
from phi.vectordb.pgvector import PgVector2

from ai.settings import ai_settings
from db.session import db_url

from phi.storage.assistant.postgres import PgAssistantStorage

# Set up logging
logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True

knowledge_base = CombinedKnowledgeBase(
    sources=[
        PDFKnowledgeBase(path="data/coffee/pdfs"),
    ],
    vector_db=PgVector2(
        db_url=db_url,
        # Store the embeddings in ai.coffee_documents
        collection="coffee_knowledge_base",
        embedder=OpenAIEmbedder(model=ai_settings.embedding_model),
    ),
    # 2 references are added to the prompt
    num_documents=2,
)

storage = PgAssistantStorage(
    db_url=db_url,
    table_name="coffee_storage",
)


def get_coffee_assistant(
    run_id: Optional[str] = None,
    user_id: Optional[str] = None,
    debug_mode: bool = False,
) -> Assistant:
    """Get an Autonomous Assistant with a coffee knowledge base."""

    return Assistant(
        name="coffee_assistant",
        run_id=run_id,
        user_id=user_id,
        llm=OpenAILike(
            model="gpt-3.5-turbo",
            api_key=getenv("LEPTON_API_KEY"),
            base_url="https://kfxrnfa5-pail-test.tin.lepton.run/api/v1/",
        ),
        storage=storage,
        knowledge_base=knowledge_base,
        # Enable monitoring on phidata.app
        # monitoring=True,
        use_tools=False,
        debug_mode=debug_mode,
        description="You are a helpful assistant named 'Max' designed to answer questions about Max's Coffee Shop.",
        extra_instructions=[
            "Keep your answers under 5 sentences.",
        ],
        assistant_data={"assistant_type": "autonomous"},
    )
