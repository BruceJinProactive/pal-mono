import json
import re
import uuid
from typing import List

from sqlalchemy.orm import Session

from ai.assistants.gym_assistant import get_gym_assistant
from ai.assistants.pizza_assistant import get_pizza_assistant
from api.models.message import AuthorType, Extras, Message, TextObject
from db.repositories.message_repository import MessageRepository
from services import assistant_service, user_service
from services.account_service import get_account

RECIPIENT_ACCOUNT_MAPPING = {
    "+14244859440": "proactiveailab",
    "+14244705958": "mindzero",
    "+14244680365": "pizzamyheart",
}


def get_chat_response(db: Session, message: Message) -> Message:
    """
    Processes an incoming message and generates a response from the appropriate assistant.

    This function performs the following steps:
    1. Identifies the account based on the recipient's channel identifier.
    2. Retrieves the account and project information.
    3. Retrieves or creates a user based on the sender's channel identifier.
    4. Saves the incoming message to the database.
    5. Retrieves the appropriate assistant based on the account name.
    6. Generates a response from the assistant.
    7. Handles different response types (Iterator, str, BaseModel).
    8. Creates and returns a new Message object for the response.
    9. Saves the response message to the database.

    Args:
        db (Session): The database session.
        message (Message): The incoming message object.

    Returns:
        Message: The response message object.

    Raises:
        ValueError: If any required information (account name, account, projects, user, assistant ID) is not found.
        ValueError: If the response type from the assistant is unexpected.
    """
    # Get account with channel identifier (assume channel platform is SMS)
    channel_identifier = message.recipient_channel_identifier

    # If the channel identifier is a phone number, convert it to an account name
    if re.match(r"^\+\d{11}$", channel_identifier):
        account_name = RECIPIENT_ACCOUNT_MAPPING.get(channel_identifier)
    else:
        account_name = channel_identifier

    if account_name is None:
        raise ValueError("Account name not found")

    # Get account and project via account name
    account = get_account(db, account_name=account_name)
    if account is None:
        raise ValueError("Account not found")

    # Get user_id by sender channel/number with user_service
    user = user_service.get_user(
        db=db,
        account_id=account.id,
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

    if not account.projects:
        raise ValueError("No projects found for this account")
    project = account.projects[0]

    assistant_id = project.assistant_id
    if assistant_id is None:
        raise ValueError("Assistant ID not found")

    if account_name == "proactiveailab":
        assistant = assistant_service.get_phi_assistant(
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
    messages = MessageRepository(db).get_messages_by_conversation(
        conversation_id=conversation_id
    )
    return messages
