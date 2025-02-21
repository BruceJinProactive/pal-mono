from typing import Any

from pydantic import BaseModel

# TODO: Support output structure


class Input(BaseModel):
    """
    A class used to represent an Input.

    content : str
        The actual content from the user, for example "Hi there, What services or features do you offer?".
    context : str, optional
        The context of the input, such as device info, membership information, etc. (default is an empty string).
    """

    content: str
    context: str = ""
    memories: str = ""
    channel: str = ""

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
            + f"<memories>{self.memories}</memories>\n\n"
            + f"<channel>{self.channel}</channel>\n\n"
        )


# TODO: Support output structure, streaming, etc.
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
    """

    content: str
    documents: list[Any] = []
    images: list[Any] = []
