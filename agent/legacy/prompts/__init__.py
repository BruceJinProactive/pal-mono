from typing import Any

from agno.memory.agent import AgentMemory

from . import _implementation


def get_system_prompt(
    raw_config: dict[str, Any],
    memory: AgentMemory,
    user_id: str,
) -> str:
    """
    Currently generates a markdown-formatted system prompt from the raw_config JSON data.

    The JSON data can have the keys "character" and "guardrails" either at the
    first level or nested under a "system_prompt" key.

    Args:
        raw_config (dict[str, Any]): The input JSON data containing the agent's and project's configuration.
        memory (AgentMemory): The memory object associated with the user.
        user_id (str): The ID of the user associated with this agent.

    Returns:
        str: A markdown-formatted string representing the system prompt.

    Example:
        json_data = {
            "system_prompt": {
                "character": {
                    "name": "Assistant",
                    "role": "Helper",
                    "traits": ["Helpful", "Friendly"]
                },
                "guardrails": {
                    "rules": ["Do not provide medical advice", "Be respectful"]
                }
            }
        }

        or

        json_data = {
            "character": {
                "name": "Assistant",
                "role": "Helper",
                "traits": ["Helpful", "Friendly"]
            },
            "guardrails": {
                "rules": ["Do not provide medical advice", "Be respectful"]
            }
        }

        Output:
        ## Character Description
        - **Name:** Assistant
        - **Roles:** Helper
        - **Traits:**
          - Helpful
          - Friendly
        ## Guardrails - Rules you must absolutely obey
        - **Topic Whitelist:**
          - Do not provide medical advice
        - **Behavioral Guidelines:**
          - Be respectful
        ## Existing Memories
          - Jane Doe's phone number is 555-555-5555
          - Jane Doe's email is jane@proactiveailab.com
    """
    return _implementation.generate_markdown_system_prompt(raw_config, memory, user_id)


__all__ = [
    "get_system_prompt",
]
