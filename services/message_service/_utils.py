import re
from typing import Any, List

from agent.input_output import Input, Output
from api.schemas.chat.message import (
    AuthorType,
    Channel,
    Extras,
    MediaObject,
    Message,
    TextObject,
    Type,
)
from utils.log import logger


def strip_markdown_content(agent_message: Any) -> Any | str:
    """
    Strip the given agent message by removing markdown formatting.

    This function processes the input string to:
    1. Remove bold markdown (**text**).
    2. Replace markdown links ([text](URL)) with just the URLs.
    3. Remove leading exclamation marks from URLs (left over from image markdown).

    Args:
        agent_message (Any): The message content to be stripped of markdown. If the input is not a string, it will be returned as is.

    Returns:
        Any | str: The stripped message content if the input was a string, otherwise the original input.
    """
    # Only process if agent_message if it is a string
    if not isinstance(agent_message, str):
        return agent_message

    # Remove bold markdown
    agent_message = re.sub(r"\*\*(.*?)\*\*", r"\1", agent_message)

    # Remove markdown links and replace with URLs
    agent_message = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\2", agent_message)

    # Remove leading exclamation mark from URLs (left over from image markdown)
    agent_message = re.sub(r"!\s*(https?://[^\s]+)", r"\1", agent_message)

    return agent_message


def remove_image_links(agent_message: Any) -> Any | str:
    """
    Remove image links (Markdown-style image links) from a given message.

    This function processes the input string to:
    1. Remove image markdown format ![alt text](URL).
    2. Remove any standalone URLs pointing to image files (e.g., .jpg, .png, .gif).

    Args:
        agent_message (Any): The message content to be stripped of image links.
                             If the input is not a string, it will be returned as is.

    Returns:
        Any | str: The message content without image links if the input was a string,
                   otherwise the original input.
    """
    # Only process if agent_message is a string
    if not isinstance(agent_message, str):
        return agent_message

    # Remove markdown-style image links ![alt text](URL)
    agent_message = re.sub(r"!\[.*?\]\((https?://[^\s]+)\)", "", agent_message)

    # Remove standalone image URLs (jpg, png, gif, etc.)
    agent_message = re.sub(
        r"https?://[^\s]+(?:\.jpg|\.jpeg|\.png|\.gif|\.bmp|\.svg)", "", agent_message
    )

    return agent_message


def extract_image_links(response: str) -> list[tuple[str, str]]:
    """
    Process response text to extract image URLs
    Returns the original text and any image URLs found.

    Args:
        response: The response text to process

    Returns:
        list[tuple[str, str]]: List of tuples containing (type, content)
            where type is either "text" or "image"
    """
    processed_parts = []

    # 1. Keep response text unchanged
    if response.strip():
        processed_parts.append(("text", response))

    # 2. Extract image URLs
    pattern = r"""
        (https?:\/\/                # http:// or https://
        [^\s)]+\.                  # URL path until extension (no spaces or closing parens)
        (?i:                       # Case insensitive match for extensions
            jpg|jpeg|png|apng|     # Common image formats
            gif|webp|svg|bmp|      # More image formats
            tiff?|ico|             # Even more formats
            heic|heif|avif|        # Modern formats
            jfif|pjpeg|pjp         # JPEG variants
        )
        (?:\/[^\s)]*)?            # Optional additional path segments
        (?:[?#][^\s)]*)?          # Optional query params or hash fragments
        )
    """
    try:
        image_urls = re.findall(pattern, response, re.VERBOSE)
        for url in image_urls:
            processed_parts.append(("image", url))
    except re.error as e:
        logger.error(f"Error extracting image URLs: {e}")

    return processed_parts


def get_agent_input_from_message(message: Message) -> Input:
    """
    Converts a Message object into an Input object for the Agent.

    Args:
        message (Message): The Message object to be converted.

    Returns:
        Input: The Input object created from the Message.
    """
    content = message.text.body if message.text else ""
    return Input(
        content=content,
        context=message.context,
        channel=message.channel,
        sender_identifier=message.sender_identifier,
    )


def get_messages_from_agent_output(
    output: Output, input_message: Message, metadata: dict[str, Any] = {}
) -> List[Message]:
    """
    Converts an Output object from the Agent into a Message object.

    Args:
        output (Output): The Output object to be converted.

    Returns:
        List[Message]: The Message object created from the Output.
    """

    # NOTE: For now we only support returning image documents

    msg_text = f"{output.content}"
    # if output.documents:
    #     msg_text += f"\n\nDocuments:\n{output.documents}"
    # if output.images:
    #     msg_text += f"\n\nImages:\n{output.images}"

    response_messages = []

    # Check if output.content contains http or .net and create additional SMS response if input_message.channel is VOICE
    if (
        re.search(r"http[s]?://|\.net", output.content)
        and input_message.channel == Channel.VOICE
    ):
        voice_msg_text = "Please head over to the payment link sent to your SMS messages to finalize your order. Thank you for choosing Pizza My Heart!"
        response_message_voice = Message(
            author_type=AuthorType.AGENT,
            sender_identifier=input_message.recipient_identifier,
            recipient_identifier=input_message.sender_identifier,
            channel=input_message.channel,
            broker=input_message.broker,
            text=TextObject(body=voice_msg_text),
            metadata=metadata,  # TODO: to be replaced by input_message.channel_info
            extras=Extras(
                escalated=output.escalated,
                closing_conversation=output.closing_conversation,
            ),
        )
        response_messages.append(response_message_voice)

        response_message_sms = Message(
            author_type=AuthorType.AGENT,
            sender_identifier=input_message.recipient_identifier,
            recipient_identifier=input_message.sender_identifier,
            channel=Channel.SMS,
            broker=input_message.broker,
            text=TextObject(body=msg_text),
            metadata=metadata,  # TODO: to be replaced by input_message.channel_info
            extras=Extras(
                escalated=output.escalated,
                closing_conversation=output.closing_conversation,
            ),
        )
        response_messages.append(response_message_sms)

    # Check if input_message.channel is API and output.content contains a link
    elif (
        re.search(r"http[s]?://", output.content)
        and input_message.channel == Channel.API
    ):
        response_parts = extract_image_links(msg_text)

        for msg_type, msg_content in response_parts:
            if msg_type == "text":
                msg_content = strip_markdown_content(msg_content)
                msg_content = remove_image_links(msg_content)
                response_message_text = Message(
                    author_type=AuthorType.AGENT,
                    sender_identifier=input_message.recipient_identifier,
                    recipient_identifier=input_message.sender_identifier,
                    channel=input_message.channel,
                    broker=input_message.broker,
                    text=TextObject(body=msg_content),
                    metadata=metadata,  # TODO: to be replaced by input_message.channel_info
                    extras=Extras(
                        escalated=output.escalated,
                        closing_conversation=output.closing_conversation,
                    ),
                )
                response_messages.append(response_message_text)
            elif msg_type == "image":
                response_message_image = Message(
                    author_type=AuthorType.AGENT,
                    sender_identifier=input_message.recipient_identifier,  # Swap sender and recipient
                    recipient_identifier=input_message.sender_identifier,
                    channel=input_message.channel,
                    broker=input_message.broker,
                    type=Type.MEDIA,
                    text=TextObject(body=msg_content),
                    media=MediaObject(
                        url=msg_content, media_type="image", caption=msg_content
                    ),
                    metadata=metadata,
                    extras=Extras(
                        escalated=output.escalated,
                        closing_conversation=output.closing_conversation,
                    ),
                )
                response_messages.append(response_message_image)

    else:
        response_message = Message(
            author_type=AuthorType.AGENT,
            sender_identifier=input_message.recipient_identifier,
            recipient_identifier=input_message.sender_identifier,
            channel=input_message.channel,
            broker=input_message.broker,
            text=TextObject(body=msg_text),
            metadata=metadata,  # TODO: to be replaced by input_message.channel_info
            extras=Extras(
                escalated=output.escalated,
                closing_conversation=output.closing_conversation,
            ),
        )
        response_messages.append(response_message)

    return response_messages
