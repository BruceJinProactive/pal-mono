import uuid
from typing import Any, Dict, List, Optional

from phi.assistant import Assistant as PhiAssistant
from sqlalchemy.orm import Session

from db.tables import Assistant

from . import _implementation


def get_ai_assistant(
    db: Session,
    assistant_id: uuid.UUID,
    user_id: uuid.UUID,
    new_run: bool = False,
) -> PhiAssistant:
    """
    Retrieve a PhiAssistant instance based on the provided assistant ID and user ID.

    Args:
        db (Session): The database session to use for the query.
        assistant_id (uuid.UUID): The unique identifier of the assistant.
        user_id (uuid.UUID): The unique identifier of the user.
        new_run (bool, optional): Flag indicating whether this is a new run. Defaults to False.

    Returns:
        PhiAssistant: The retrieved PhiAssistant instance.
    """
    return _implementation.get_ai_assistant(db, assistant_id, user_id, new_run)


def get_assistant(db: Session, assistant_id: uuid.UUID) -> Optional[Assistant]:
    """
    Retrieve an Assistant instance based on the provided assistant ID.

    Args:
        db (Session): The database session to use for the query.
        assistant_id (uuid.UUID): The unique identifier of the assistant.

    Returns:
        Optional[Assistant]: The retrieved Assistant instance if found, otherwise None.
    """
    return _implementation.get_assistant(db, assistant_id)


def get_assistants_by_account(db: Session, account_name: str) -> List[Assistant]:
    """
    Retrieve a list of Assistants instance based on the provided assistant ID.

    Args:
        db (Session): The database session to use for the query.
        account_name (str): The unique identifier of the assistant.

    Returns:
        List[Assistant]: Return the list of assistants
    """
    return _implementation.get_assistants_by_account(db, account_name)


def update_assistant_config(
    db: Session, assistant_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Update the raw_config of the assistant associated with the provided assistant ID.

    Args:
        db (Session): The database session to use for the update.
        assistant_id (uuid.UUID): The unique identifier of the assistant.
        config (Dict[str, Any]): A dictionary containing the configuration settings to update.

    Returns:
        None
    """
    return _implementation.update_assistant_config(db, assistant_id, config)


def replace_assistant_config(
    db: Session, assistant_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    """
    Replace the raw_config of the assistant associated with the provided assistant ID.

    Args:
        db (Session): The database session to use for the update.
        assistant_id (uuid.UUID): The unique identifier of the assistant.
        config (Dict[str, Any]): A dictionary containing the new configuration settings.

    Returns:
        None
    """
    return _implementation.replace_assistant_config(db, assistant_id, config)


__all__ = [
    "get_ai_assistant",
    "get_assistant",
    "get_assistants_by_account",
    "update_assistant_config",
    "replace_assistant_config",
]
