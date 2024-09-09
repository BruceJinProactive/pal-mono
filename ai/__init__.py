from typing import Any, Dict

from phi.assistant import Assistant

from . import _assistants


def integrate_assistant(
    account_name: str,
    user_id: str,
    raw_config: Dict[str, Any],
    new_run: bool = False,
) -> Assistant:
    """
    Integrate and configure an AI assistant for a specific account and user.

    This function sets up storage, knowledge base, and memory for the assistant,
    and configures it based on the provided raw configuration.

    Args:
        account_name (str): The name of the account for which the assistant is being integrated.
        user_id (str): The ID of the user associated with this assistant.
        raw_config (Dict[str, Any]): A dictionary containing the assistant's configuration,
                                     typically converted from JSON.
        new_run (bool, optional): If True, starts a new run. If False, attempts to
                                  continue from the last run. Defaults to False.

    Returns:
        Assistant: A configured Assistant object ready for use.

    Note:
        This function uses global settings from ai_settings and db_url.
        The assistant is configured with debug mode enabled and default tools.
    """

    return _assistants.integrate_assistant(
        account_name=account_name,
        user_id=user_id,
        raw_config=raw_config,
        new_run=new_run,
    )
