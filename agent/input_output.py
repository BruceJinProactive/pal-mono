from typing import Any, List

from pydantic import BaseModel, Field

from utils.request_context import RequestContext


class Message(BaseModel):
    """
    A class used to represent a message in the conversation history.

    role : str
        The role of the message sender, either "user" or "assistant".
    content : str
        The content of the message.
    """

    role: str
    content: str
    context: str
    channel: str
    sender_identifier: str


class Input(BaseModel):
    """
    A class used to represent an Input.

    content : str
        The actual content from the user, for example "Hi there, What services or
        features do you offer?".
    context : str, optional
        The context of the input, such as device info, membership information, etc.
        (default is an empty string).
    stream : bool, optional
        Whether to stream the output (default is False).
        If True, the response will be streamed as AsyncIterator[Output].
        If False, the response will be a single Output.
    """

    content: str
    context: str = ""
    channel: str = ""
    sender_identifier: str = ""
    stream: bool = False
    history_messages: List[Message] = []
    request_context: RequestContext = Field(exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def get_prompt(self):
        """
        Constructs a model message from the content and context.

        str
            A formatted string containing the content and context.
        """

        # TODO: Update prompts here
        return (
            f"<content>{self.content}</content>\n\n"
            + f"<context>{self.context}</context>\n\n"
            + f"<channel>{self.channel}</channel>\n\n"
            + f"<sender_identifier>{self.sender_identifier}</sender_identifier>\n\n"
        )


class Output(BaseModel):
    """
    A class used to represent an Output.

    content : str
        The actual content from the agent, for example "As a coffee barista, I offer a
        variety of services and features to enhance your coffee experience.\n\nFeel free
        to let me know if there's anything specific you'd like to know!".

    documents : list, optional
        A list of documents that can be used to provide additional information
        (default is an empty list). Examples include, a menu of the services offered.

    images : list, optional
        A list of images retrieved.

    escalated : bool, optional
        Whether the response should be escalated to a human (default is False).

    closing_conversation : bool, optional
        Whether the conversation should be closed (default is False).
    """

    content: str
    documents: list[Any] = []
    images: list[Any] = []

    # Extras
    escalated: bool = False
    closing_conversation: bool = False
