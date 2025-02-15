from agno.tools.toolkit import Toolkit
from pydantic import BaseModel, Field, create_model

from . import _implementation


def get_tools(agent_raw_config, user_id, session_id):
    """
    Initialize and return a list of toolkits based on the agent raw configuration.

    Args:
        agent_raw_config (dict): The raw configuration dictionary containing toolkit configurations.
        user_id (str): The user ID.
        session_id (str): The session ID.

    Returns:
        list: A list of initialized toolkit instances.

    Raises:
        KeyError: If the toolkit name is not found in the toolkit_map.
        TypeError: If the "tools" key is not a list or if the "config" key is not a dictionary.

    Example:
        agent_raw_config = {
            "tools": [
                {
                    "toolkit": "OrderingTools",
                    "config": {"api_key": "your_api_key", "api_secret": "your_api_secret"}
                },
                {
                    "toolkit": "BookingTools",
                    "config": {"api_key": "another_api_key", "api_secret": "another_api_secret"}
                }
            ]
        }
        tools = get_tools(agent_raw_config)
    """
    return _implementation.get_tools(agent_raw_config, user_id, session_id)


def generate_output_model(tools: list[Toolkit]):
    """
    Dynamically generate a Pydantic model to structure the output of the LLM,
    based on necessary fields as determined by the toolkits used.

    Args:
        tools (list[Toolkit]): A list of toolkit instances used by the assistant.

    Returns:
        OutputModel: A Pydantic model class that structures the output of the LLM.
    """
    return _implementation.generate_output_model(tools)


__all__ = ["get_tools", "generate_output_model"]
