from dataclasses import dataclass

import db


@dataclass
class UserSessionPreview:
    user_session: db.Conversation
    last_message: db.Message
    message_count: int


@dataclass
class CognitoUserSession:
    user_sub: str
    access_token: str
    refresh_token: str
    id_token: str
    expires_in: int


@dataclass
class CognitoUser:
    email: str
    name: str
    session: CognitoUserSession | None = None
