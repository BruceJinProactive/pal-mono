import copy
import os
from typing import Any
from uuid import uuid4

from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import agent
from phi.agent.agent import Agent

from agent.legacy.knowledge import get_knowledge
from agent.legacy.memory import get_history_responses, get_memory
from agent.legacy.prompts import get_system_prompt
from agent.legacy.storage import get_storage
from agent.model import get_model
from tools.legacy import generate_output_model, get_tools


@agent
def integrate_agent(
    agent_id: str,
    account_name: str,
    agent_raw_config: dict[str, Any],
    project_raw_config: dict[str, Any],
    user_id: str,
    conversation_id: str | None = None,
    new_run: bool = False,
    stream: bool = False,
) -> Agent:
    # Merge project configuration into agent configuration
    raw_config = merge_configs(agent_raw_config, project_raw_config)

    # -*- Agent settings
    model = get_model(stream=stream)

    # -*- Agent Memory
    memory = get_memory(account_name, raw_config)
    num_history_responses = get_history_responses(raw_config)

    # -*- Agent Knowledge
    knowledge = get_knowledge(account_name)

    # -*- Agent Storage
    storage = get_storage(account_name)

    # -*- System Prompt Settings
    system_prompt = get_system_prompt(raw_config, memory, user_id)

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
    tools = get_tools(raw_config, user_id, session_id)

    # -*- Structured Output Model
    output_model = generate_output_model(tools)

    # -*- Debug settings
    DEBUG_MODE = os.getenv("DEBUG_MODE", "False") == "True"

    # Set up Datadog LLM Observability
    LLMObs.enable(
        ml_app=account_name,
        agentless_enabled=True,
    )
    LLMObs.annotate(tags={"user_id": user_id, "session_id": conversation_id})

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


def merge_configs(
    agent_config: dict[str, Any], project_config: dict[str, Any]
) -> dict[str, Any]:
    """
        Merge project configuration into agent configuration. If a field exists in both,
        the project configuration field will replace the agent configuration field.
    ``
        Args:
            agent_config (dict[str, Any]): The agent's configuration.
            project_config (dict[str, Any]): The project's configuration.

        Returns:
            dict[str, Any]: The merged configuration.
    """
    # NOTE: you can use shallow .copy() to speed up performance, but it will alter agent_config parameter, as long as you are aware
    merged_config = copy.deepcopy(agent_config)

    for key, value in project_config.items():
        if key == "tools" and isinstance(value, list):
            agent_tools = {
                tool["toolkit"]: tool
                for tool in merged_config.get("tools", [])
                if "toolkit" in tool
            }
            for tool in value:
                toolkit = tool.get("toolkit")
                if not toolkit:
                    continue
                if toolkit in agent_tools:
                    agent_tools[toolkit]["config"] = merge_configs(
                        agent_tools[toolkit].get("config", {}), tool.get("config", {})
                    )
                else:
                    agent_tools[toolkit] = tool
            merged_config["tools"] = list(agent_tools.values())
        elif (
            isinstance(value, dict)
            and key in merged_config
            and isinstance(merged_config[key], dict)
        ):
            merged_config[key] = merge_configs(merged_config[key], value)
        else:
            merged_config[key] = value
    return merged_config
