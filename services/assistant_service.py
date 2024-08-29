import uuid
from typing import Any, Dict, Optional

from phi.assistant import Assistant as PhiAssistant
from phi.assistant import AssistantMemory
from phi.embedder.openai import OpenAIEmbedder
from phi.knowledge.combined import CombinedKnowledgeBase
from phi.memory.db.postgres import PgMemoryDb
from phi.storage.assistant.postgres import PgAssistantStorage
from phi.vectordb.pgvector import PgVector2
from sqlalchemy.orm import Session

from ai.llm import LLM, get_llm
from ai.settings import ai_settings
from db.repositories.assistant_repository import AssistantRepository
from db.session import db_url
from db.tables import Assistant


def get_phi_assistant(
    db: Session,
    assistant_id: uuid.UUID,
    user_id: uuid.UUID,
    new_run: bool = False,
) -> PhiAssistant:
    # Retrieve the assistant from the database
    assistant_repository = AssistantRepository(db)
    assistant = assistant_repository.get_assistant(assistant_id=assistant_id)

    # Set up the knowledge base, storage, and memory
    if assistant is None:
        raise ValueError("Invalid assistant_id")
    account_name = assistant.account.name
    storage_table_name = f"{account_name}_storage"
    knowledge_base_table_name = f"{account_name}_knowledge_base"
    memory_table_name = f"{account_name}_memory"

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

    storage = PgAssistantStorage(
        db_url=db_url,
        table_name=storage_table_name,
    )

    memory = AssistantMemory(
        db=PgMemoryDb(
            db_url=db_url,
            table_name=memory_table_name,
        ),
    )

    run_id = None
    if not new_run:
        run_ids = storage.get_all_run_ids(user_id=str(user_id))
        run_id = run_ids[0] if run_ids else None

    # Retrive the assistant configs from the database
    # raw_config = assistant.raw_config
    # TODO: Save the assistant configs in the database
    raw_config = {
        "name": "Pal Test Assistant",
        "description": "A conversational assistant that can help you order coffee.",
        "instructions": [
            "Tell me what you want to order and I'll help you out.",
            "I can also provide information about our menu.",
        ],
        "extra_instructions": ["Keep your answers under 5 sentences."],
    }
    name = raw_config.get("name", "")
    descripton = raw_config.get("description", "")
    instructions = raw_config.get("instructions", [])
    extra_instructions = raw_config.get(
        "extra_instructions", ["Keep your answers under 5 sentences."]
    )

    return PhiAssistant(
        # Hardcoded assistant fields
        run_id=run_id,
        user_id=str(user_id),
        llm=get_llm(LLM.OPENAI),
        # Assistant settings
        use_tools=True,
        show_tool_calls=True,
        search_knowledge=True,
        read_chat_history=True,
        create_memories=True,
        update_memory_after_run=True,
        debug_mode=True,
        # Assistant db tables
        storage=storage,
        knowledge_base=knowledge_base,
        memory=memory,
        # Assistant configurations
        name=name,
        description=descripton,
        instructions=instructions,
        extra_instructions=extra_instructions,
        assistant_data={"assistant_type": "autonomous"},
    )


def get_assistant(db: Session, assistant_id: uuid.UUID) -> Optional[Assistant]:
    # Retrieve the assistant from the database
    assistant_repository = AssistantRepository(db)
    assistant = assistant_repository.get_assistant(assistant_id=assistant_id)
    return assistant


def update_assistant_config(
    db: Session, assistant_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    assistant_repository = AssistantRepository(db)
    assistant_repository.update_assistant_config(
        assistant_id=assistant_id, config=config
    )


def replace_assistant_config(
    db: Session, assistant_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    assistant_repository = AssistantRepository(db)
    assistant_repository.replace_assistant_config(
        assistant_id=assistant_id, config=config
    )
