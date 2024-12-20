import os
from typing import Any
from uuid import uuid4

from phi.agent.agent import Agent

from agent.knowledge import get_knowledge
from agent.memory import get_history_responses, get_memory
from agent.model import generate_output_model, get_model
from agent.prompts import get_system_prompt
from agent.storage import get_storage
from tools import get_tools


def integrate_agent(
    agent_id: str,
    account_name: str,
    agent_raw_config: dict[str, Any],
    user_id: str,
    conversation_id: str | None = None,
    new_run: bool = False,
    stream: bool = False,
) -> Agent:
    # -*- Agent settings
    model = get_model(stream=stream)

    # -*- Agent Memory
    memory = get_memory(account_name, agent_raw_config)
    num_history_responses = get_history_responses(agent_raw_config)

    # -*- Agent Knowledge
    knowledge = get_knowledge(account_name)

    # -*- Agent Storage
    storage = get_storage(account_name)

    # -*- System Prompt Settings
    system_prompt = get_system_prompt(agent_raw_config, memory, user_id)

    # -*- Session settings
    session_id = str(uuid4())
    if conversation_id:
        session_id = conversation_id
    elif not new_run:
        session_ids = storage.get_all_session_ids(
            user_id=str(user_id), agent_id=agent_id
        )
        session_id = session_ids[0] if session_ids else str(uuid4())

    # -*- Agent Tools
    tools = get_tools(agent_raw_config, user_id, session_id)

    # -*- Structured Output Model
    output_model = generate_output_model(tools)

    # -*- Debug settings
    DEBUG_MODE = os.getenv("DEBUG_MODE", "False") == "True"

    return Agent(
        # -*- Agent settings
        provider=model,
        agent_id=agent_id,
        agent_data={"agent_type": "autonomous"},
        # -*- User settings
        user_id=user_id,
        # -*- Session settings
        session_id=session_id,
        # -*- Agent Memory
        memory=memory,
        add_chat_history_to_messages=True,
        num_history_responses=num_history_responses,
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
        output_model=None if stream else output_model,
        parse_response=True,
        structured_outputs=False,  # please set to False for JSON mode
        # -*- Debug settings
        debug_mode=DEBUG_MODE,
    )
