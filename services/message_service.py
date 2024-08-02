import logging
from typing import Iterator

from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.models.message import AuthorType, Message, TextObject
from services import assistant_service, user_service

# Set up logging
logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True


def get_chat_response(db: Session, message: Message) -> Message:
    # Get user_id by sender channel/number with user_service
    user_id = user_service.get_user_id(db=db)

    # Get assistant_id with recipient channel/number with assistant_service
    assistant_id = assistant_service.get_assistant_id(
        db=db,
    )

    # Get assistant with assistant_id and user_id with assistant_service
    assistant = assistant_service.get_assistant(
        db=db, assistant_id=assistant_id, user_id=user_id
    )

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
    return Message(
        author_type=AuthorType.ASSISTANT,
        sender_channel_identifier=message.recipient_channel_identifier,  # Swap sender and recipient
        recipient_channel_identifier=message.sender_channel_identifier,
        channel_platform=message.channel_platform,
        messaging_broker=message.messaging_broker,
        text=TextObject(body=response_content),
        metadata=message.metadata,  # Preserve original metadata
    )
