from . import _implementation


def generate_system_prompt(json_data) -> str:
    """
    Currently generates a markdown-formatted system prompt from the raw_config JSON data.

    The JSON data can have the keys "character" and "guardrails" either at the
    first level or nested under a "system_prompt" key.

    Args:
        json_data (dict): The input JSON data containing character description
                          and guardrails.

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
    """
    return _implementation.generate_markdown_system_prompt(json_data)


__all__ = [
    "generate_system_prompt",
]
