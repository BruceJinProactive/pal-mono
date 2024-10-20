import uuid
from typing import List

from sqlalchemy.orm import Session

import db.tables as db
from ai.llm import OutputModel
from api.schemas.message.message import AuthorType, Extras, Message, TextObject
from db.repositories.conversation_repository import ConversationRepository
from db.repositories.message_repository import MessageRepository
from db.repositories.project_repository import ProjectRepository
from db.tables import Conversation
from services import assistant_service, user_service
from utils.log import logger


async def get_chat_response(db: Session, message: Message) -> Message:
    user = None
    extras = {}

    try:
        # find project with matching channel platform, identifier pair
        project_channel_identifier = (
            f"{message.channel_platform.value}:{message.recipient_channel_identifier}"
        )
        project = ProjectRepository(db).get_project_by_channel_identifier(
            project_channel_identifier
        )

        if project is None:
            raise ValueError(
                f"Project with channel platform '{message.channel_platform.value}', channel_identifier '{message.recipient_channel_identifier}' not found."
            )

        # Get user_id by sender channel/number with user_service
        user_channel_identifier = (
            f"{message.channel_platform.value}:{message.sender_channel_identifier}"
        )
        user = user_service.get_user_by_channel_identifier(
            db=db,
            account_id=project.account_id,
            channel_identifier=user_channel_identifier,
            create_new_user=True,
        )

        if user is None:
            raise ValueError("User not found")

        # Save request message to database
        MessageRepository(db).create_message(
            user_id=user.id, message_body=message.to_dict()
        )

        # Get appropriate assistant from account name
        assistant_id = project.assistant_id
        if assistant_id is None:
            raise ValueError("Assistant ID not found")

        assistant = assistant_service.get_ai_assistant(
            db=db, assistant_id=assistant_id, user_id=user.id
        )

        # Get response from assistant
        response_object = await assistant.arun(message.text.body, stream=False)
        if isinstance(response_object, str):
            response = response_object
        elif isinstance(response_object, OutputModel):
            response = response_object.content
            extras = {"escalated": response_object.escalated}
        else:
            raise ValueError(
                f"Can't handle response type {type(response_object)} for userid {user.id} with text msg {message.text.body}."
            )
    except Exception as e:
        # Log any error and set default error response
        logger.error(e)
        response = "Something went wrong. Please try again."

    response_message = Message(
        author_type=AuthorType.ASSISTANT,
        sender_channel_identifier=message.recipient_channel_identifier,  # Swap sender and recipient
        recipient_channel_identifier=message.sender_channel_identifier,
        channel_platform=message.channel_platform,
        messaging_broker=message.messaging_broker,
        text=TextObject(body=response),
        metadata={"instance": "BaseModel"},
        extras=Extras(**extras),
    )

    if user:
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
        return [new_conversation] if new_conversation else []

    return []


def get_conversations_by_users(
    db: Session, user_ids: List[uuid.UUID]
) -> List[Conversation]:
    conversation_repository = ConversationRepository(db)
    return conversation_repository.get_conversations_by_users(
        user_ids=user_ids,
    )
