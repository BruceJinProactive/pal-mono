from typing import Any

from phi.memory.agent import AgentMemory


def format_section(title, section_data):
    """
    Format a section of the markdown output.

    Args:
        title (str): The title of the section.
        section_data (dict): The data for the section.

    Returns:
        list: A list of formatted strings for the section.
    """
    formatted_section = [f"## {title}"]
    for key, value in section_data.items():
        formatted_key = key.replace("_", " ").title()
        if isinstance(value, list):
            formatted_section.append(f"- **{formatted_key}:**")
            for item in value:
                formatted_section.append(f"  - {item}")
        else:
            formatted_section.append(f"- **{formatted_key}:** {value}")
    return formatted_section


def generate_markdown_system_prompt(
    raw_config: dict[str, Any],
    memory: AgentMemory,
    user_id: str,
) -> str:
    markdown_output = []
    # Determine the level at which character and guardrails are located
    # Note: this may change in the future
    if "system_prompt" in raw_config:
        data = raw_config["system_prompt"]
    else:
        data = raw_config

    # Process character description
    character_description = data.get("character")
    if character_description:
        markdown_output.extend(
            format_section("Character Description", character_description)
        )

    # Process guardrails
    guardrails = data.get("guardrails")
    if guardrails:
        markdown_output.extend(
            format_section("Guardrails - Rules you must absolutely obey", guardrails)
        )

    # Process memories
    memory.user_id = user_id
    memory.load_user_memories()
    memories = memory.memories
    memory_list = (
        "\n".join(f"  - {memory.memory}" for memory in memories) if memories else ""
    )
    if memory_list:
        markdown_output.append("## Existing Memories")
        markdown_output.append(memory_list)

    # Join all parts into a single string with new lines
    return "\n".join(markdown_output)
