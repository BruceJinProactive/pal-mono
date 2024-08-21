from typing import Iterator

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai.assistants.gym_assistant import get_gym_assistant
from ai.assistants.pizza_assistant import get_pizza_assistant
from api.models.message import AuthorType, Message, TextObject
from db.repositories.message_repository import MessageRepository
from services import assistant_service, user_service
from services.admin_service import get_account


def get_chat_response(db: Session, message: Message) -> Message:
    # Get account with chnannel identifier (assume channel platform is SMS)
    channel_identifier = message.recipient_channel_identifier
    recipient_account_mapping = {
        "+14244859440": "proactiveailab",
        "+14244705958": "mindzero",
        "+14244680365": "pizzamyheart",
    }
    account_name = recipient_account_mapping.get(channel_identifier)
    if account_name is None:
        raise ValueError("Account name not found")

    # Get account and project via account name
    account = get_account(db, account_name=account_name)
    if account is None:
        raise ValueError("Account not found")
    if not account.projects:
        raise ValueError("No projects found for this account")
    project = account.projects[0]

    # Get user_id by sender channel/number with user_service
    user = user_service.get_user(
        db=db,
        project_id=str(project.id),
        channel_platform=message.channel_platform.value,  # Need .value, otherwise the value is CHANNELPLATFORM.WHATSAPP
        channel_identifier=message.sender_channel_identifier,
        create_new_user=True,
    )
    if user is None:
        raise ValueError("User not found")

    # Save request message to database
    MessageRepository(db).create_message(
        user_id=str(user.id), message_body=message.to_dict()
    )

    assistant_id = project.assistants[0].id
    if assistant_id is None:
        raise ValueError("Assistant ID not found")

    if account_name == "proactiveailab":
        assistant = assistant_service.get_assistant(
            db=db, assistant_id=str(assistant_id), user_id=str(user.id)
        )
    elif account_name == "mindzero":
        assistant = get_gym_assistant(user_id=str(user.id))
    elif account_name == "pizzamyheart":
        assistant = get_pizza_assistant(user_id=str(user.id))

    # Get response from assistant
    response = assistant.run(message.text.body, stream=False)

    # Handle different response types
    if isinstance(response, Iterator):
        response_content = "".join(response)
    elif isinstance(response, str):
        response_content = response
    elif isinstance(response, BaseModel):
        response_content = response.model_dump_json()
    else:
        raise ValueError("Unexpected response type from get_chat_response")

    # Create and return a new Message object for the response
    response_message = Message(
        author_type=AuthorType.ASSISTANT,
        sender_channel_identifier=message.recipient_channel_identifier,  # Swap sender and recipient
        recipient_channel_identifier=message.sender_channel_identifier,
        channel_platform=message.channel_platform,
        messaging_broker=message.messaging_broker,
        text=TextObject(body=response_content),
        metadata=message.metadata,  # Preserve original metadata
    )

    # Save response message to database
    MessageRepository(db).create_message(
        user_id=str(user.id), message_body=response_message.to_dict()
    )

    return response_message
