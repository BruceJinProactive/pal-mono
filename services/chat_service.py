import logging
from typing import Iterator

from pydantic import BaseModel
from sqlalchemy.orm import Session

from services import assistant_service, user_service

# Set up logging
logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True


def get_chat_response(
    db: Session, channel: str, sender: str, recipient: str, content: str
) -> str:
    # Get user_id by sender channel/number with user_service
    user_id = user_service.get_user_id(db=db, channel=channel, sender=sender)

    # Get assistant with recipient channel/number with assistant_service
    assistant_id = assistant_service.get_assistant_id(
        db=db, channel=channel, recipient=recipient, user_id=user_id
    )
    assistant = assistant_service.get_assistant(
        db=db, assistant_id=assistant_id, user_id=user_id
    )

    response = assistant.run(content, stream=False)
    # Handle different response types
    if isinstance(response, Iterator):
        response_content = "".join(response)
    elif isinstance(response, str):
        response_content = response
    elif isinstance(response, BaseModel):
        response_content = response.model_dump_json()
    else:
        raise ValueError("Unexpected response type from get_chat_response")

    return response_content
