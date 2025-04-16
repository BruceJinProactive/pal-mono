import json

from agno.tools.toolkit import Toolkit
from ddtrace.llmobs import LLMObs
from ddtrace.llmobs.decorators import tool

from agent.legacy.storage import get_storage
from utils.log import logger

from ... import _config


class QueryMessagesTool(Toolkit):
    def __init__(self, metadata: _config.ToolMetadata):
        super().__init__(name="query_messages_tool")
        self.register(self.query_messages)
        self.metadata = metadata

    # NOTE: `latest_user_message` is currently required since Agno does not write a message
    # to the Agno Storage until after all function calls / generations have been made.
    # We can remove this once we migrate to our own solution.
    @tool
    def query_messages(self, latest_user_message: str) -> str:
        """Use this function to get the chat history.

        Args:
            latest_user_message (str): The latest user message in the chat history.

        Returns:
            str: A string representing the entire chat history.
        """

        try:
            try:
                LLMObs.annotate(metadata=self.metadata.model_dump())

                chat_history = ""
                storage = get_storage(self.metadata.account_name)
                agent_session = storage.read(
                    str(self.metadata.session_id), str(self.metadata.user_id)
                )

                if not agent_session:
                    logger.error(
                        "Agent session not found for\n"
                        f"Account Name: {self.metadata.account_name}\n"
                        f"Account ID: {self.metadata.account_id}\n"
                        f"Agent ID: {self.metadata.agent_id}\n"
                        f"User ID: {self.metadata.user_id}\n"
                        f"Session ID: {self.metadata.session_id}"
                    )

                    if latest_user_message:
                        chat_history += f"**[User]**\n{latest_user_message}\n\n"
                        return chat_history

                    return "Agent session not found"

                messages = agent_session.memory["runs"]  # type: ignore

                for message in messages:
                    role = message["message"]["role"]
                    if role == "user":
                        user_content = message["message"]["content"]
                        chat_history += f"**[User]**\n{user_content}\n\n"

                        assistant_response = json.loads(message["response"]["content"])
                        assistant_content = assistant_response["content"]
                        chat_history += f"**[Assistant]**\n{assistant_content}\n\n"
                    else:
                        logger.info(
                            f"Skipping appending message to chat history:\n{message}"
                        )

                chat_history += f"**[User]**\n{latest_user_message}"

                LLMObs.annotate(output_data=chat_history)

                return chat_history

            except ValueError:
                logger.error(
                    "Conversation history not found for\n"
                    f"Account ID: {self.metadata.account_id}\n"
                    f"Agent ID: {self.metadata.agent_id}\n"
                    f"User ID: {self.metadata.user_id}\n"
                    f"Session ID: {self.metadata.session_id}"
                )

                return "Conversation history not found."

        except Exception as e:
            error_msg = "Error in getting chat history"
            logger.error(f"{error_msg}: {e}")
            return error_msg
