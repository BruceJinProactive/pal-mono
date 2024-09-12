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


def generate_markdown_system_prompt(json_data) -> str:
    markdown_output = []

    # Determine the level at which character and guardrails are located
    if "system_prompt" in json_data:
        data = json_data["system_prompt"]
    else:
        data = json_data

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

    # Join all parts into a single string with new lines
    return "\n".join(markdown_output)
