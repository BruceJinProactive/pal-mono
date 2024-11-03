from typing import Any, Dict

from phi.assistant.assistant import Assistant

from ai.knowledge import get_knowledge
from ai.llm import OutputModel, get_model
from ai.memory import get_memory
from ai.prompts import get_system_prompt
from ai.storage import get_storage
from ai.tools import get_tools


def integrate_assistant(
    account_name: str,
    assistant_raw_config: Dict[str, Any],
    user_id: str,
    conversation_id: str | None = None,
    new_run: bool = False,
) -> Assistant:
    # Set up llm
    llm = get_model()

    # Set up memory
    memory = get_memory(account_name)

    # Retrieve and build prompts and add memory list
    system_prompt = get_system_prompt(assistant_raw_config, memory, user_id)

    # Set up storage
    storage = get_storage(account_name)

    # Set up knowledge base
    knowledge = get_knowledge(account_name)

    # Add tools
    tools = get_tools(assistant_raw_config, user_id)

    # Get run id
    run_id = None
    if conversation_id:
        run_id = conversation_id
    elif not new_run:
        run_ids = storage.get_all_run_ids(user_id=str(user_id))
        run_id = run_ids[0] if run_ids else None

    return Assistant(
        # Assistant settings
        assistant_data={"assistant_type": "autonomous"},
        # Run settings
        run_id=run_id,
        # User settings
        user_id=user_id,
        # Chat Memory
        add_chat_history_to_messages=True,
        add_chat_history_to_prompt=False,
        num_history_messages=10,
        # Prompt Settings
        system_prompt=system_prompt,
        # Storage, knowledge, and memory
        storage=storage,
        knowledge_base=knowledge,
        memory=memory,
        create_memories=True,
        update_memory_after_run=True,
        # LLM
        llm=llm,
        # Tools
        tools=tools,
        use_tools=True,
        show_tool_calls=False,
        search_knowledge=True,
        read_chat_history=True,
        # Configurations
        debug_mode=False,
        # Output Format
        output_model=OutputModel,
    )
