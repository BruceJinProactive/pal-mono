import uuid
from typing import AsyncIterator, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

import db
from ai.model import OutputModel
from api.schemas.chat.message import (
    AuthorType,
    Extras,
    MediaObject,
    Message,
    TextObject,
)
from api.schemas.chat.message import Type as MessageType
from services import agent_service, user_service
from utils.log import logger


async def get_chat_response_async(
    session: AsyncSession, message: Message
) -> list[Message]:
    user = None
    extras = {}
    message_repo = db.MessageRepositoryAsync(session)
    response_messages = []
    try:
        # find project with matching channel platform, identifier pair
        project_channel_identifier = (
            f"{message.channel.value}:{message.recipient_identifier}"
        )
        project_repo = db.ProjectRepositoryAsync(session)
        project = await project_repo.get_project_by_channel_identifier(
            project_channel_identifier
        )
        if project is None:
            raise ValueError(
                f"Project with channel platform '{message.channel.value}', channel_identifier '{message.recipient_identifier}' not found."
            )

        # Get user_id by sender channel/number with user_service
        user_channel_identifier = f"{message.channel.value}:{message.sender_identifier}"
        user_repo = db.UserRepositoryAsync(session)
        user = await user_repo.get_user_by_channel_identifier(
            account_id=project.account_id,
            channel_identifier=user_channel_identifier,
        )
        if user is None:
            user = await user_repo.create_user(
                project.account_id, user_channel_identifier
            )

        # Save request message to database
        request_message = await message_repo.create_message(
            user_id=user.id, message_body=message.to_dict()
        )
        if not request_message:
            raise ValueError("Failed to create request message")
        conversation_id = request_message.conversation_id

        # Get appropriate agent from account name
        agent_id = project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")
        agent = await agent_service.get_ai_agent_async(
            session=session,
            agent_id=agent_id,
            user_id=user.id,
            conversation_id=conversation_id,
        )

        # Get response from agent
        request_content = message.get_content()
        response_object = await agent.arun(request_content, stream=False)
        response_content = response_object.content
        if isinstance(response_content, str):
            response = response_content
        elif isinstance(response_content, OutputModel):
            response = response_content.content
            extras = {"escalated": response_content.escalated}
            response_parts = process_regex(response)

            # process each part of the response after regex processing
            response_message = None
            for msg_type, msg_content in response_parts:
                if msg_type == "text":
                    response_message = Message(
                        author_type=AuthorType.AGENT,
                        sender_identifier=message.recipient_identifier,  # Swap sender and recipient
                        recipient_identifier=message.sender_identifier,
                        channel=message.channel,
                        broker=message.broker,
                        text=TextObject(body=msg_content),
                        metadata={"instance": "BaseModel"},
                        extras=Extras(**extras),
                    )
                elif msg_type == "image":
                    response_message = Message(
                        author_type=AuthorType.AGENT,
                        sender_identifier=message.recipient_identifier,  # Swap sender and recipient
                        recipient_identifier=message.sender_identifier,
                        channel=message.channel,
                        broker=message.broker,
                        type=MessageType.MEDIA,
                        media=MediaObject(
                            url=msg_content, media_type="image", caption=msg_content
                        ),
                        metadata={"instance": "BaseModel"},
                        extras=Extras(**extras),
                    )

                if response_message:
                    if user:
                        # Save response message to database
                        await message_repo.create_message(
                            user_id=user.id, message_body=response_message.to_dict()
                        )

                    response_messages.append(response_message)
        else:
            raise ValueError(
                f"Can't handle response content type {type(response_content)} for userid {user.id} with request content {request_content}."
            )

    except Exception:
        # Log any error and set default error response
        logger.exception("Error in get_chat_response")
        response = "Something went wrong. Please try again."

    return response_messages


async def get_chat_response_stream(
    session: AsyncSession, message: Message
) -> AsyncIterator[Message]:
    user = None
    message_repo = db.MessageRepositoryAsync(session)

    async def error_response_generator() -> AsyncIterator[Message]:
        error_message = Message(
            author_type=AuthorType.AGENT,
            sender_identifier=message.recipient_identifier,
            recipient_identifier=message.sender_identifier,
            channel=message.channel,
            broker=message.broker,
            text=TextObject(body="Something went wrong. Please try again."),
            metadata={"instance": "BaseModel"},
            extras=Extras(),
        )
        yield error_message

    try:
        # find project with matching channel platform, identifier pair
        project_channel_identifier = (
            f"{message.channel.value}:{message.recipient_identifier}"
        )
        project_repo = db.ProjectRepositoryAsync(session)
        project = await project_repo.get_project_by_channel_identifier(
            project_channel_identifier
        )
        if project is None:
            raise ValueError(
                f"Project with channel platform '{message.channel.value}', channel_identifier '{message.recipient_identifier}' not found."
            )

        # Get user_id by sender channel/number with user_service
        user_channel_identifier = f"{message.channel.value}:{message.sender_identifier}"
        user_repo = db.UserRepositoryAsync(session)
        user = await user_repo.get_user_by_channel_identifier(
            account_id=project.account_id,
            channel_identifier=user_channel_identifier,
        )
        if user is None:
            user = await user_repo.create_user(
                project.account_id, user_channel_identifier
            )

        # Save request message to database
        request_message = await message_repo.create_message(
            user_id=user.id, message_body=message.to_dict()
        )
        if not request_message:
            raise ValueError("Failed to create request message")
        conversation_id = request_message.conversation_id

        # Get appropriate agent from account name
        agent_id = project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")
        agent = await agent_service.get_ai_agent_async(
            session=session,
            agent_id=agent_id,
            user_id=user.id,
            conversation_id=conversation_id,
            stream=True,
        )

        # Get response from agent
        request_content = message.get_content()
        response_stream = await agent.arun(request_content, stream=True)
        return response_stream

    except Exception:
        # Log any error and return error message stream
        logger.exception("Error in get_chat_response_stream")
        return error_response_generator()


def get_chat_response(session: Session, message: Message) -> Message:
    user = None
    metadata = {"instance": "BaseModel"}
    extras = {}

    try:
        # find project with matching channel platform, identifier pair
        project_channel_identifier = (
            f"{message.channel.value}:{message.recipient_identifier}"
        )
        project = db.ProjectRepository(session).get_project_by_channel_identifier(
            project_channel_identifier
        )

        if project is None:
            raise ValueError(
                f"Project with channel platform '{message.channel.value}', channel_identifier '{message.recipient_identifier}' not found."
            )

        metadata["project_name"] = project.name

        # Get user_id by sender channel/number with user_service
        user_channel_identifier = f"{message.channel.value}:{message.sender_identifier}"
        user = user_service.get_user_by_channel_identifier(
            session=session,
            account_id=project.account_id,
            channel_identifier=user_channel_identifier,
            create_new_user=True,
        )

        if user is None:
            raise ValueError("User not found")

        # Save request message to database
        request_message = db.MessageRepository(session).create_message(
            user_id=user.id, message_body=message.to_dict()
        )
        conversation_id = request_message.conversation_id

        # Get appropriate agent from account name
        agent_id = project.agent_id
        if agent_id is None:
            raise ValueError("Agent ID not found")

        agent = agent_service.get_ai_agent(
            session=session,
            agent_id=agent_id,
            user_id=user.id,
            conversation_id=conversation_id,
        )

        # Get response from agent
        request_content = message.get_content()
        response_object = agent.run(request_content, stream=False)
        if isinstance(response_object.content, str):
            response = response_object.content
        elif isinstance(response_object.content, OutputModel):
            response = response_object.content.content
            extras = {"escalated": response_object.content.escalated}
        else:
            raise ValueError(
                f"Can't handle response content type {type(response_object.content)} for userid {user.id} with request content {request_content}."
            )

    except Exception as e:
        # Log any error and set default error response
        logger.error(e)
        response = "Something went wrong. Please try again."

    response_message = Message(
        author_type=AuthorType.AGENT,
        sender_identifier=message.recipient_identifier,  # Swap sender and recipient
        recipient_identifier=message.sender_identifier,
        channel=message.channel,
        broker=message.broker,
        text=TextObject(body=response),
        metadata=metadata,
        extras=Extras(**extras),
    )

    if user:
        # Save response message to database
        db.MessageRepository(session).create_message(
            user_id=user.id, message_body=response_message.to_dict()
        )

    return response_message


def get_messages_by_conversation(
    session: Session, conversation_id: uuid.UUID
) -> List[db.Message]:
    """
    Retrieves all Messages for a given Conversation.

    This function queries the database to fetch all Messages associated with the specified Conversation ID.

    Args:
        session (Session): The database connection.
        conversation_id (uuid.UUID): The unique identifier of the Conversation for which Messages are being retrieved.

    Returns:
        List[db.Message]: A list of Message objects representing the messages in the specified Conversation.
    """
    messages = db.MessageRepository(session).get_messages_by_conversation(
        conversation_id=conversation_id
    )
    return messages


def get_conversations_by_user(
    session: Session, user_id: uuid.UUID, create_new_conversation: bool = False
) -> List[db.Conversation]:
    conversation_repository = db.ConversationRepository(session)
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
    session: Session, user_ids: List[uuid.UUID]
) -> List[db.Conversation]:
    conversation_repository = db.ConversationRepository(session)
    return conversation_repository.get_conversations_by_users(
        user_ids=user_ids,
    )


def create_conversation(session: Session, user_id: uuid.UUID) -> db.Conversation | None:
    conversation_repository = db.ConversationRepository(session)
    return conversation_repository.create_conversation(user_id=user_id)


def process_regex(markdown_text: str) -> list[tuple[str, str]]:
    """
    Process markdown text to extract image URLs and split text into parts.

    Args:
        markdown_text: The markdown text to process

    Returns:
        list[str]: List of text parts with image markdown removed
    """
    import re

    pattern = r"!?\[.*?\]\((https?:\/\/[^\s)]+)\)"
    processed_parts = []
    last_end = 0

    try:
        for match in re.finditer(pattern, markdown_text):
            start, end = match.span()
            # Extract text before the image
            if start > last_end:
                text_part = markdown_text[last_end:start].strip()
                if text_part:
                    processed_parts.append(("text", text_part))
            # Extract the image URL
            image_url = match.group(1)
            processed_parts.append(("image", image_url))
            last_end = end
        # Extract any remaining text after the last image
        if last_end < len(markdown_text):
            text_part = markdown_text[last_end:].strip()
            if text_part:
                processed_parts.append(("text", text_part))
        return processed_parts

    except re.error as e:
        logger.error(f"Error processing markdown: {e}")
        return [("text", markdown_text)]
