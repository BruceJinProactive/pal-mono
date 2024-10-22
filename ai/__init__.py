from typing import Any, Dict

from phi.assistant.assistant import Assistant

from . import _implementation


def integrate_assistant(
    account_name: str,
    assistant_raw_config: Dict[str, Any],
    user_id: str,
    conversation_id: str | None = None,
    new_run: bool = False,
) -> Assistant:
    """
    Integrate and configure an AI assistant for a specific account and user.

    This function sets up storage, knowledge base, and memory for the assistant,
    and configures it based on the provided raw configuration.

    Args:
        account_name (str): The name of the account for which the assistant is being integrated.
        assistant_raw_config (Dict[str, Any]): A dictionary containing the assistant's configuration,
                                               typically converted from JSON.
        user_id (str): The ID of the user associated with this assistant.
        conversation_id (str | None, optional): The ID of the conversation associated with this assistant.
                                                If None, a new conversation is created. Defaults to None.
        new_run (bool, optional): If True, starts a new run. If False, attempts to
                                  continue from the last run. Defaults to False.

    Returns:
        Assistant: A configured Assistant object ready for use.

    Note:
        This function uses global settings from ai_settings and db_url.
        The assistant is configured with debug mode enabled and default tools.
    """

    return _implementation.integrate_assistant(
        account_name=account_name,
        assistant_raw_config=assistant_raw_config,
        user_id=user_id,
        conversation_id=conversation_id,
        new_run=new_run,
    )
