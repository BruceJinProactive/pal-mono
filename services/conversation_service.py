from typing import List

from sqlalchemy.orm import Session

import db.tables as db
from db.repositories.conversation_repository import ConversationRepository


def get_conversations_by_user(
    db: Session, user_id: str, create_new_conversation: bool = False
) -> List[db.Conversation]:
    conversation_repository = ConversationRepository(db)
    conversations = conversation_repository.get_conversations_by_user(
        user_id=user_id,
    )

    if conversations:
        return conversations

    if create_new_conversation:
        new_conversation = conversation_repository.create_conversation(user_id=user_id)
        return [new_conversation]

    return []
