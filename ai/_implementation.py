from typing import Any, Dict

from phi.assistant.assistant import Assistant

from ai.knowledge import get_knowledge_base
from ai.llm import get_llm
from ai.memory import get_memory
from ai.prompts import get_system_prompt
from ai.storage import get_storage


def integrate_assistant(
    account_name: str,
    assistant_raw_config: Dict[str, Any],
    user_id: str,
    new_run: bool = False,
) -> Assistant:
    # Set up llm
    llm = get_llm()

    # Retrive and build prompts
    system_prompt = get_system_prompt(assistant_raw_config)

    # Set up storage
    storage = get_storage(account_name)

    # Set up knowledge base
    knowledge_base = get_knowledge_base(account_name)

    # Set up memory
    memory = get_memory(account_name)

    # TODO: Add tools

    # Get run id
    run_id = None
    if not new_run:
        run_ids = storage.get_all_run_ids(user_id=str(user_id))
        run_id = run_ids[0] if run_ids else None

    return Assistant(
        # Basic fields
        user_id=user_id,
        run_id=run_id,
        # Prompts
        system_prompt=system_prompt,
        assistant_data={"assistant_type": "autonomous"},
        # Storage, knowledge base, and memory
        storage=storage,
        knowledge_base=knowledge_base,
        memory=memory,
        create_memories=True,
        update_memory_after_run=True,
        # LLM
        llm=llm,
        # Tools
        tools=[],
        use_tools=True,
        show_tool_calls=True,
        search_knowledge=True,
        read_chat_history=True,
        # Configurations
        debug_mode=True,
    )
