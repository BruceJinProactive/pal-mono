import datetime
import uuid
from typing import AsyncGenerator, List, Optional

from agno.run.response import RunResponse
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
)
from openai.types.chat.chat_completion import Choice as FinalChoice
from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice
from openai.types.chat.chat_completion_chunk import ChoiceDelta
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.chat.message import AuthorType, Channel
from api.schemas.chat.message import Message as PalMessage
from api.schemas.chat.message import Metadata, TextObject
from services.message_service import get_chat_response_async, get_chat_response_stream
from utils.log import logger


def extract_user_text(messages: List[ChatCompletionMessageParam]) -> str:
    # return the last text content of the last user message
    for m in messages[::-1]:
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


class ChatCompletionStreamer:

    def _gen_id(self):
        return f"chatcmpl-{uuid.uuid4().hex}"

    async def stream_chat(
        self,
        messages: List[ChatCompletionMessageParam],
        recipient_identifier: str,
        session: AsyncSession,
    ) -> AsyncGenerator[bytes, None]:

        user_msg = extract_user_text(messages)
        logger.info(f"Received message: {user_msg}")
        response_stream = await get_chat_response_stream(
            session=session,
            message=PalMessage(
                author_type=AuthorType.USER,
                sender_identifier="user_id",  # get the phone number.
                recipient_identifier=recipient_identifier,
                channel=Channel.VOICE,
                text=TextObject(body=user_msg),
                metadata=Metadata(),
            ),
        )
        logger.info("Received response stream")
        if response_stream:
            i = 0
            async for chunk in response_stream:
                rid = self._gen_id()
                if isinstance(chunk, RunResponse):
                    content = chunk.get_content_as_string()
                elif isinstance(chunk, tuple):
                    content = chunk[0]
                elif isinstance(chunk, PalMessage):
                    content = chunk.text.body if chunk.text else ""
                    rid = chunk.id
                elif chunk:
                    if not isinstance(chunk, (str, int, float, bool)):
                        logger.warning(f"Unexpected chunk type: {type(chunk)}")
                        continue
                    content = str(chunk)
                else:
                    content = ""
                logger.info(f"Sending chunk: {content}")
                chunk = ChatCompletionChunk(
                    id=rid,
                    object="chat.completion.chunk",
                    created=int(
                        datetime.datetime.now(datetime.timezone.utc).timestamp()
                    ),
                    model=recipient_identifier,
                    choices=[
                        ChunkChoice(
                            index=i,
                            delta=(ChoiceDelta(role="assistant", content=content)),
                            finish_reason=None,
                        )
                    ],
                )
                yield f"data: {chunk.model_dump_json()}\n\n".encode("utf-8")
                i += 1
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
                sender_identifier="user_id",  # phone number
                recipient_identifier=recipient_identifier,
                channel=Channel.VOICE,
                text=TextObject(body=user_msg),
                metadata=Metadata(),  # TODO: add metadata, e.g., project name
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
