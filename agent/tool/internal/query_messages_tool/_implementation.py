import uuid
from typing import Dict

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from db.repositories.message_repository import MessageRepository
from db.session import get_db
from utils.log import logger

from ... import _config


class QueryMessagesTool(Toolkit):
    def __init__(self, metadata: _config.ToolMetadata):
        super().__init__(name="query_messages_tool")
        self.register(self.query_messages)
        self.metadata = metadata

    @tool
    def query_messages(self, latest_user_message: str) -> str:
        """Use this function to get the chat history.

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: A string representing the entire chat history.
        """

        try:
            LLMObs.annotate(metadata=self.metadata.model_dump())

            chat_history = ""

            # The session_id in the metadata is actually the conversation_id in the database
            conversation_id = uuid.UUID(str(self.metadata.session_id))

            # Get database session using the context manager provided by db/session.py
            # Use the generator from get_db() function

            db_generator = get_db()
            db = next(db_generator)

            try:
                # Initialize repositories
                message_repo = MessageRepository(db)

                # Get all messages for this conversation in chronological order
                messages = message_repo.get_messages_by_conversation(conversation_id)
                logger.debug(
                    f"QueryMessagesTool queries conversation: {conversation_id} and gets messages: {messages}"
                )

                if not messages and not latest_user_message:
                    return "Conversation not found"

                # Format each message into the chat history
                for message in messages:
                    body: Dict = message.body
                    if "author_type" in body:
                        if body["author_type"] == "user":
                            # User message
                            if "text" in body and "body" in body["text"]:
                                user_content = body["text"]["body"]
                                chat_history += f"**[User]**\n{user_content}\n\n"
                        elif body["author_type"] == "agent":
                            # Agent/Assistant message
                            if "text" in body and "body" in body["text"]:
                                assistant_content = body["text"]["body"]
                                chat_history += (
                                    f"**[Assistant]**\n{assistant_content}\n\n"
                                )

                chat_history += f"**[User]**\n{latest_user_message}\n\n"

                LLMObs.annotate(output_data=chat_history)

                return chat_history

            finally:
                # Exhaust the generator to ensure proper cleanup
                try:
                    next(db_generator, None)
                except StopIteration:
                    pass

        except Exception as e:
            error_msg = "Error in getting chat history"
            logger.error(f"{error_msg}: {e}")
            return error_msg
