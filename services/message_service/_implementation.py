import json
import re
import uuid
from typing import List

from sqlalchemy.orm import Session

import db.tables as db
from ai.assistants.gym_assistant import get_gym_assistant
from ai.assistants.pizza_assistant import get_pizza_assistant
from api.models.message import AuthorType, Extras, Message, TextObject
from db.repositories.conversation_repository import ConversationRepository
from db.repositories.message_repository import MessageRepository
from db.repositories.project_repository import ProjectRepository
from db.tables import Conversation
from services import assistant_service, user_service


def get_chat_response(db: Session, message: Message) -> Message:
    # find project with matching channel platform, identifier pair
    project = ProjectRepository(db).get_project_by_channel(
        channel_platform=message.channel_platform.value,  # Need .value, otherwise the value is a CHANNELPLATFORM object
        channel_identifier=message.recipient_channel_identifier,
    )

    if project is None:
        raise ValueError(
            f"Project with channel platform '{message.channel_platform.value}', channel_identifier '{message.recipient_channel_identifier}' not found."
        )

    # Get user_id by sender channel/number with user_service
    user = user_service.get_user_by_channel(
        db=db,
        account_id=project.account_id,
        channel_platform=message.channel_platform.value,  # Need .value, otherwise the value is CHANNELPLATFORM.WHATSAPP
        channel_identifier=message.sender_channel_identifier,
        create_new_user=True,
    )
    if user is None:
        raise ValueError("User not found")

    # Save request message to database
    MessageRepository(db).create_message(
        user_id=user.id, message_body=message.to_dict()
    )

    account_name = project.account.name
    # Get appropriate assistant from account name
    if account_name == "proactiveailab":
        assistant_id = project.assistant_id
        if assistant_id is None:
            raise ValueError("Assistant ID not found")

        assistant = assistant_service.get_ai_assistant(
            db=db, assistant_id=assistant_id, user_id=user.id
        )
    elif account_name == "mindzero":
        assistant = get_gym_assistant(user_id=str(user.id))
    elif account_name == "pizzamyheart":
        assistant = get_pizza_assistant(user_id=str(user.id))

    # Get response from assistant
    response = assistant.run(message.text.body, stream=False)

    pattern = r"^(.*?)###(.*)###$"
    match = re.match(pattern, response, re.DOTALL)

    if match:
        content = match.group(1).strip()
        extras = json.loads(match.group(2))
    else:
        content = response
        extras = {}

    response_message = Message(
        author_type=AuthorType.ASSISTANT,
        sender_channel_identifier=message.recipient_channel_identifier,  # Swap sender and recipient
        recipient_channel_identifier=message.sender_channel_identifier,
        channel_platform=message.channel_platform,
        messaging_broker=message.messaging_broker,
        text=TextObject(body=content),
        metadata={"instance": "BaseModel"},
        extras=Extras(**extras),
    )

    # Save response message to database
    MessageRepository(db).create_message(
        user_id=user.id, message_body=response_message.to_dict()
    )

    return response_message


def get_messages_by_conversation(
    db: Session, conversation_id: uuid.UUID
) -> List[Message]:
    """
    Retrieves all Messages for a given Conversation.

    This function queries the database to fetch all Messages associated with the specified Conversation ID.

    Args:
        db (Session): The database connection.
        conversation_id (uuid.UUID): The unique identifier of the Conversation for which Messages are being retrieved.

    Returns:
        List[Message]: A list of Message objects representing the messages in the specified Conversation.
    """
    messages = MessageRepository(db).get_messages_by_conversation(
        conversation_id=conversation_id
    )
    return messages


def get_conversations_by_user(
    db: Session, user_id: uuid.UUID, create_new_conversation: bool = False
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


def get_conversations_by_users(
    db: Session, user_ids: List[uuid.UUID]
) -> List[Conversation]:
    conversation_repository = ConversationRepository(db)
    return conversation_repository.get_conversations_by_users(
        user_ids=user_ids,
    )
