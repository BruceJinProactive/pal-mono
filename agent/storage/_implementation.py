import uuid

from ddtrace.llmobs.decorators import task

from agent.input_output import Message
from db import MessageRepositoryAsync
from db.session import AsyncSessionLocal
from utils.dd import safe_annotate


@task(name="Query History Messages")
async def query_history_messages(
    conversation_id: uuid.UUID, limit: int = 100
) -> list[Message]:
    async with AsyncSessionLocal() as db:
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
        safe_annotate(
            tags={
                "conversation_id": conversation_id,
                "history_messages": len(history_messages),
            }
        )
        return history_messages
