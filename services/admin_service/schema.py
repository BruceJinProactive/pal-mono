from dataclasses import dataclass

import db


@dataclass
class UserSessionPreview:
    user_session: db.Conversation
    last_message: db.Message
    message_count: int


@dataclass
class CognitoUser:
    email: str
    name: str
