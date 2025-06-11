import uuid

from agent.input_output import Message
from db import MessageRepositoryAsync
from db.session import AsyncSessionLocal
from utils.log import logger


async def query_history_messages(
    conversation_id: uuid.UUID, limit: int = 20
) -> list[Message]:
    async with AsyncSessionLocal() as db:
        logger.debug(f"[Storage] Query history_messages on {conversation_id}")
        message_repo = MessageRepositoryAsync(db)
        messages = await message_repo.get_messages_by_conversation(
            conversation_id, limit
        )
        history_messages = []
        for message in messages:
            body = message.body
            role = "user" if body.get("author_type") == "user" else "assistant"
            content = body.get("text", {}).get("body", "")
            context = body.get("context", "")
            channel = body.get("channel", "")
            sender_identifier = body.get("sender_identifier", "")
            history_messages.append(
                Message(
                    role=role,
                    content=content,
                    context=context,
                    channel=channel,
                    sender_identifier=sender_identifier,
                )
            )
        return history_messages
