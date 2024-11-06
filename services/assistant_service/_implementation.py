import uuid
from typing import Any, Dict, List, Optional

from phi.agent.agent import Agent as PhiAgent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ai import integrate_agent
from db.repositories.account_repository import AccountRepository
from db.repositories.assistant_repository import (
    AssistantRepository,
    AssistantRepositoryAsync,
)
from db.tables import Assistant


async def get_ai_agent_async(
    db: AsyncSession,
    assistant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> PhiAgent:
    # Retrieve the assistant from the database
    assistant_repository = AssistantRepositoryAsync(db)
    assistant = await assistant_repository.get_assistant(assistant_id=assistant_id)

    if assistant is None:
        raise ValueError("Invalid assistant_id")

    # Assuming integrate_assistant is a synchronous function
    return integrate_agent(
        agent_id=str(assistant_id),
        account_name=assistant.account.name,
        agent_raw_config=assistant.raw_config,
        user_id=str(user_id),
        conversation_id=str(conversation_id),
    )


def get_ai_agent(
    db: Session,
    assistant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    new_run: bool = False,
) -> PhiAgent:
    # Retrieve the assistant from the database
    assistant_repository = AssistantRepository(db)
    assistant = assistant_repository.get_assistant(assistant_id=assistant_id)
    if assistant is None:
        raise ValueError("Invalid assistant_id")

    return integrate_agent(
        agent_id=str(assistant_id),
        account_name=assistant.account.name,
        agent_raw_config=assistant.raw_config,
        user_id=str(user_id),
        conversation_id=str(conversation_id) if conversation_id else None,
        new_run=new_run,
    )


def get_assistant(db: Session, assistant_id: uuid.UUID) -> Optional[Assistant]:
    # Retrieve the assistant from the database
    assistant_repository = AssistantRepository(db)
    assistant = assistant_repository.get_assistant(assistant_id=assistant_id)
    return assistant


def get_assistants_by_account(
    db: Session, account_name: str
) -> Optional[List[Assistant]]:
    # Retrieve the assistant from the database
    account_repository = AccountRepository(db)
    account = account_repository.get_account(account_name)
    assistants = []
    if account:
        account_id = account.id
        assistants = AssistantRepository(db).get_assistants_by_account(
            account_id=account_id
        )
    return assistants


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
