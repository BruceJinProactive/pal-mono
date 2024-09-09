from typing import Any, Dict

from phi.assistant import Assistant, AssistantMemory
from phi.embedder.openai import OpenAIEmbedder
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.memory.db.postgres import PgMemoryDb
from phi.storage.assistant.postgres import PgAssistantStorage
from phi.vectordb.pgvector import PgVector2

from ai.llm import LLM, get_llm
from ai.settings import ai_settings
from db.session import db_url


def integrate_assistant(
    account_name: str,
    user_id: str,
    raw_config: Dict[str, Any],
    new_run: bool = False,
) -> Assistant:
    # Set up storage
    storage_table_name = f"{account_name}_storage"
    storage = PgAssistantStorage(
        db_url=db_url,
        table_name=storage_table_name,
    )

    # Set up knowledge base
    knowledge_base_table_name = f"{account_name}_knowledge_base"
    knowledge_base = CombinedKnowledgeBase(
        sources=[],
        vector_db=PgVector2(
            db_url=db_url,
            collection=knowledge_base_table_name,
            embedder=OpenAIEmbedder(model=ai_settings.embedding_model),
        ),
        # 2 references are added to the prompt
        num_documents=2,
    )

    # Set up memory
    memory_table_name = f"{account_name}_memory"
    memory = AssistantMemory(
        db=PgMemoryDb(
            db_url=db_url,
            table_name=memory_table_name,
        ),
    )

    # Get run id
    run_id = None
    if not new_run:
        run_ids = storage.get_all_run_ids(user_id=str(user_id))
        run_id = run_ids[0] if run_ids else None

    # Retrive and build prompts
    # TODO: Adopt prompt template
    name = raw_config.get("name", "")
    descripton = raw_config.get("description", "")
    instructions = raw_config.get("instructions", [])
    extra_instructions = raw_config.get(
        "extra_instructions", ["Keep your answers under 5 sentences."]
    )

    # TODO: Add tools

    return Assistant(
        # Basic fields
        user_id=user_id,
        run_id=run_id,
        # Prompts
        name=name,
        description=descripton,
        instructions=instructions,
        extra_instructions=extra_instructions,
        assistant_data={"assistant_type": "autonomous"},
        # Storage, knowledge base, and memory
        storage=storage,
        knowledge_base=knowledge_base,
        memory=memory,
        create_memories=True,
        update_memory_after_run=True,
        # LLM
        llm=get_llm(LLM.ROUTER),
        # Tools
        tools=[],
        use_tools=True,
        show_tool_calls=True,
        search_knowledge=True,
        read_chat_history=True,
        # Configurations
        debug_mode=True,
    )
