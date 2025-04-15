import datetime
import uuid
from datetime import timedelta
from functools import lru_cache
from typing import AsyncGenerator, List, Optional

from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
)
from openai.types.chat.chat_completion import Choice as FinalChoice
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

import db
from api.schemas.chat.message import AuthorType, Channel, Metadata, TextObject
from api.schemas.chat.message import Message as PalMessage
from services.message_service import get_chat_response_async, get_chat_response_stream
from utils.log import logger


class MemoryCache:
    def __init__(self):
        self.store = {}  # {key: (value, expire_time)}

    def set(self, key: str, value, ttl_seconds: int = 300):
        expire_time = (
            datetime.datetime.now(datetime.timezone.utc)
            + timedelta(seconds=ttl_seconds)
            if ttl_seconds
            else None
        )
        self.store[key] = (value, expire_time)

    def get(self, key: str):
        if key not in self.store:
            return None
        value, expire_time = self.store[key]
        if expire_time and expire_time < datetime.datetime.now(datetime.timezone.utc):
            del self.store[key]
            return None
        return value

    def has(self, key: str):
        return self.get(key) is not None

    def delete(self, key: str):
        if key in self.store:
            del self.store[key]


def extract_user_text(messages: List[ChatCompletionMessageParam]) -> str:
    # return the last text content of the last user message
    for m in messages[::-1]:
        # print(m)
        if m["role"] == AuthorType.USER:
            content = m["content"]
            if isinstance(content, str):
                return content
            elif isinstance(content, list):
                # only support text contetnt, return the last text part of each message
                for part in content[::-1]:
                    if part["type"] == "text":
                        return part["text"]
    return ""


AGENT_NAMESPACE_UUID = uuid.UUID("f2a9062c-76b0-4c1d-bd75-6fdd07316807")


@lru_cache
def uuid_from_phone(phone_number: str) -> uuid.UUID:
    return uuid.uuid5(AGENT_NAMESPACE_UUID, phone_number)


FILLER_PHRASES = [
    "Sure thing.",
    "Okay, one sec.",
    "Let me see...",
    "Just a moment.",
    "Alright.",
    "Give me a second.",
]


class ChatCompletionStreamer:

    def _gen_id(self):
        return f"chatcmpl-{uuid.uuid4().hex}"

    async def stream_chat(
        self,
        messages: List[ChatCompletionMessageParam],
        recipient_identifier: str,
        session: AsyncSession,
        sender_identifier: str = "empty_number",
        memory_cache: MemoryCache = MemoryCache(),
    ) -> AsyncGenerator[bytes, None]:
        async for new_session in db.get_db_async():
            session = new_session
            user_msg = extract_user_text(messages)
            logger.info(f"Received message: {user_msg},{sender_identifier}")
            sender_identifier = str(uuid_from_phone(sender_identifier))
            message = PalMessage(
                author_type=AuthorType.USER,
                sender_identifier=sender_identifier,  # get the phone number.
                recipient_identifier=recipient_identifier,
                channel=Channel.API,
                text=TextObject(body=user_msg),
                metadata=Metadata(
                    account_name="palona-voice",
                    project_name="palona-voice-default",
                    # agent_id="82dcb010-2fb9-47f9-bb14-96ce08fed8c4",
                    user_id=sender_identifier,
                ),
            )
            message.__dict__["cache"] = memory_cache
            # setattr(message, "cache", memory_cache)
            response_stream = await get_chat_response_stream(
                session=session,
                message=message,
            )
            async for chunk in response_stream:
                yield f"data: {chunk.model_dump_json()}\n\n".encode("utf-8")

            yield b"data: [DONE]\n\n"

    async def full_response(
        self,
        messages: List[ChatCompletionMessageParam],
        recipient_identifier: str,
        session: AsyncSession,
    ) -> ChatCompletion:
        user_msg = extract_user_text(messages)
        response_messages = await get_chat_response_async(
            session=session,
            message=PalMessage(
                author_type=AuthorType.USER,
                sender_identifier="5797932533",  # phone number
                recipient_identifier=recipient_identifier,
                channel=Channel.API,
                text=TextObject(body=user_msg),
                metadata=Metadata(
                    account_name="palona-voice",
                    project_name="palona-voice-default",
                    # agent_id="82dcb010-2fb9-47f9-bb14-96ce08fed8c4",
                    # user_id="fc86a16a-9920-4b5d-89e4-6336bede31e5",
                ),  # TODO: add metadata, e.g., project name
            ),
        )
        choices = []
        i = 0
        for msg in response_messages:
            if isinstance(msg, PalMessage):
                reply = msg.text.body if msg.text else ""
            elif isinstance(msg, str):
                reply = msg
            elif isinstance(msg, tuple):
                reply = msg[0]
            else:
                logger.warning(f"Unexpected message type: {type(msg)}")
                continue
            choices.append(
                FinalChoice(
                    index=i,
                    message=ChatCompletionMessage(role="assistant", content=reply),
                    finish_reason="stop",
                )
            )
            i += 1
        return ChatCompletion(
            id=self._gen_id(),
            object="chat.completion",
            created=int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
            model=recipient_identifier,
            choices=choices,
        )


class CompletionRequest(BaseModel):
    model: str
    messages: List[ChatCompletionMessageParam]
    stream: Optional[bool] = False
