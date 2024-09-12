import uuid
from typing import Any, Dict, Optional

from phi.assistant.assistant import Assistant as AIAssistant
from sqlalchemy.orm import Session

from ai import integrate_assistant
from db.repositories.assistant_repository import AssistantRepository
from db.tables import Assistant


def get_ai_assistant(
    db: Session,
    assistant_id: uuid.UUID,
    user_id: uuid.UUID,
    new_run: bool = False,
) -> AIAssistant:
    # Retrieve the assistant from the database
    assistant_repository = AssistantRepository(db)
    assistant = assistant_repository.get_assistant(assistant_id=assistant_id)
    if assistant is None:
        raise ValueError("Invalid assistant_id")

    return integrate_assistant(
        account_name=assistant.account.name,
        assistant_raw_config=assistant.raw_config,
        user_id=str(user_id),
        new_run=new_run,
    )


def get_assistant(db: Session, assistant_id: uuid.UUID) -> Optional[Assistant]:
    # Retrieve the assistant from the database
    assistant_repository = AssistantRepository(db)
    assistant = assistant_repository.get_assistant(assistant_id=assistant_id)
    return assistant


def update_assistant_config(
    db: Session, assistant_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    assistant_repository = AssistantRepository(db)
    assistant_repository.update_assistant_config(
        assistant_id=assistant_id, config=config
    )


def replace_assistant_config(
    db: Session, assistant_id: uuid.UUID, config: Dict[str, Any]
) -> None:
    assistant_repository = AssistantRepository(db)
    assistant_repository.replace_assistant_config(
        assistant_id=assistant_id, config=config
    )
