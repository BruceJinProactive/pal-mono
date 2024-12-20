from typing import Any

from phi.agent.agent import Agent

from . import _implementation


def integrate_agent(
    agent_id: str,
    account_name: str,
    agent_raw_config: dict[str, Any],
    user_id: str,
    conversation_id: str | None = None,
    new_run: bool = False,
    stream: bool = False,
) -> Agent:
    """
    Integrate and configure an AI agent for a specific account and user.

    This function sets up storage, knowledge base, and memory for the agent,
    and configures it based on the provided raw configuration.

    Args:
        agent_id: (str): The UUID of the agent being integrated.
        account_name (str): The name of the account for which the agent is being integrated.
        agent_raw_config (Dict[str, Any]): A dictionary containing the agent's configuration,
                                               typically converted from JSON.
        user_id (str): The ID of the user associated with this agent.
        conversation_id (str | None, optional): The ID of the conversation associated with this agent.
                                                If None, a new conversation is created. Defaults to None.
        new_run (bool, optional): If True, starts a new run. If False, attempts to
                                  continue from the last run. Defaults to False.

    Returns:
        Agent: A configured Agent object ready for use.

    Note:
        This function uses global settings from ai_settings and db_url.
        The agent is configured with debug mode enabled and default tools.
    """

    return _implementation.integrate_agent(
        agent_id=agent_id,
        account_name=account_name,
        agent_raw_config=agent_raw_config,
        user_id=user_id,
        conversation_id=conversation_id,
        new_run=new_run,
        stream=stream,
    )
