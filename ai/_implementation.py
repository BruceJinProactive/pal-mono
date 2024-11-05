from typing import Any

from phi.agent.agent import Agent

from ai.knowledge import get_knowledge
from ai.llm import OutputModel, get_llm
from ai.memory import get_memory
from ai.prompts import get_system_prompt
from ai.storage import get_storage
from ai.tools import get_tools


def integrate_agent(
    agent_id: str,
    account_name: str,
    agent_raw_config: dict[str, Any],
    user_id: str,
    conversation_id: str | None = None,
    new_run: bool = False,
) -> Agent:
    # -*- Agent settings
    llm = get_llm()

    # -*- Agent Memory
    memory = get_memory(account_name)

    # -*- Agent Knowledge
    knowledge = get_knowledge(account_name)

    # -*- Agent Storage
    storage = get_storage(account_name)

    # -*- Agent Tools
    tools = get_tools(agent_raw_config, user_id)

    # -*- System Prompt Settings
    system_prompt = get_system_prompt(agent_raw_config, memory, user_id)

    # -*- Session settings
    session_id = None
    if conversation_id:
        session_id = conversation_id
    elif not new_run:
        session_ids = storage.get_all_session_ids(
            user_id=str(user_id), agent_id=agent_id
        )
        session_id = session_ids[0] if session_ids else None

    return Agent(
        # -*- Agent settings
        provider=llm,
        agent_id=agent_id,
        agent_data={"agent_type": "autonomous"},
        # -*- User settings
        user_id=user_id,
        # -*- Session settings
        session_id=session_id,
        # -*- Agent Memory
        memory=memory,
        add_chat_history_to_messages=True,
        num_history_responses=10,
        # -*- Agent Knowledge
        knowledge_base=knowledge,
        # -*- Agent Storage
        storage=storage,
        # -*- Agent Tools
        tools=tools,
        show_tool_calls=False,
        # -*- Default tools
        read_chat_history=True,
        search_knowledge=True,
        # -*- System Prompt Settings
        system_prompt=system_prompt,
        # -*- Agent Response Settings
        output_model=OutputModel,
        parse_response=True,
        structured_outputs=False,  # please set to False for JSON mode
        # -*- Agent run details
        # -*- Debugging
        debug_mode=False,
    )
