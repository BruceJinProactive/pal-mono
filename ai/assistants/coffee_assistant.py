import logging

from phi.assistant import Assistant, AssistantMemory
from phi.embedder.openai import OpenAIEmbedder
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.knowledge.pdf import PDFKnowledgeBase
from phi.memory.db.postgres import PgMemoryDb
from phi.storage.assistant.postgres import PgAssistantStorage
from phi.vectordb.pgvector import PgVector2

from ai.llm import LLM, get_llm
from ai.settings import ai_settings
from db.session import db_url

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

memory = AssistantMemory(
    db=PgMemoryDb(
        db_url=db_url,
        table_name="coffee_memory",
    ),
)


def get_coffee_assistant(
    user_id: str,
    new_run: bool = False,
    debug_mode: bool = False,
) -> Assistant:
    run_id = None
    if not new_run:
        run_ids = storage.get_all_run_ids(user_id=user_id)
        run_id = run_ids[0] if run_ids else None

    assistant = Assistant(
        name="coffee_assistant",
        run_id=run_id,
        user_id=user_id,
        llm=get_llm(LLM.OPENAI),
        storage=storage,
        knowledge_base=knowledge_base,
        create_memories=True,
        update_memory_after_run=True,
        memory=memory,
        use_tools=True,
        show_tool_calls=True,
        search_knowledge=True,
        read_chat_history=True,
        debug_mode=debug_mode,
        description="You are a helpful assistant named 'Max' designed to answer questions about Max's Coffee Shop.",
        extra_instructions=[
            "Keep your answers under 5 sentences.",
        ],
        assistant_data={"assistant_type": "autonomous"},
    )

    return assistant
