from typing import Any

from utils.log import logger

# ============================================================================
# EXCEPTIONS
# ============================================================================


class SquadCreationError(Exception):
    """Exception raised when squad creation fails."""

    pass


# ============================================================================
# PUBLIC FUNCTIONS
# ============================================================================


def get_squad_model(squad_data: dict[str, Any]) -> dict[str, Any] | None:
    """
    Get the squad model from the squad data.
    """
    # Get language assistant model name from the second member of squad_data.
    # The first member is the triage assistant, and all subsequent members function as language assistants.
    members = squad_data.get("members", [])
    if len(members) < 2:
        logger.error("Squad has fewer than two members; cannot extract language model")
        return None

    language_assistant = members[1]["assistant"]
    model_block = language_assistant.get("model")

    return model_block
