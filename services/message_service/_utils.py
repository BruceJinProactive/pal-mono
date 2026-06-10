import email
import json
import os
import re
from email import policy
from typing import Any, List

import boto3

from agent.input_output import Input, Output
from api.schemas.chat.message import (
    AuthorType,
    Extras,
    MediaObject,
    Message,
    Metadata,
    TextObject,
    Type,
)
from db.tables.types import Channel
from utils.log import logger
from utils.request_context import RequestContext


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
    Remove all instances of image links (Markdown-style image links, standalone image URLs, and <image_urls> tags) from a given message.

    This function processes the input string to:
    1. Remove all occurrences of image markdown format ![alt text](URL).
    2. Remove all standalone URLs pointing to image files (e.g., .jpg, .png, .gif, etc.).
    3. Remove everything between the <image_urls> tags and the tags themselves.
    4. Insert a blank line after each removed image link to maintain readability.

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

    # Remove all markdown-style image links ![alt text](URL) and add a blank line after removal
    # agent_message = re.sub(r"!\[.*?\]\((https?://[^\s]+)\)", "\\n\\n", agent_message)

    # Remove all standalone image URLs (jpg, jpeg, png, apng, gif, webp, svg, bmp, tiff, ico, heic, heif, avif, jfif, pjpeg, pjp) and add a blank line after removal
    agent_message = re.sub(
        r"https?://[^\s]+(?:\.jpg|\.jpeg|\.png|\.apng|\.gif|\.webp|\.svg|\.bmp|\.tiff?|\.ico|\.heic|\.heif|\.avif|\.jfif|\.pjpeg|\.pjp)",
        "\\n\\n",
        agent_message,
    )

    # Remove everything between the <image_urls> tags and the tags themselves
    agent_message = re.sub(
        r"<image_urls>.*?</image_urls>", "", agent_message, flags=re.DOTALL
    )

    # Normalize multiple consecutive newlines (avoid excessive blank lines)
    agent_message = re.sub(r"\n{3,}", "\n\n", agent_message).strip()

    return agent_message


def extract_image_links(response: str) -> list[tuple[str, str]]:
    """
    Process response text to extract image URLs. Extract everything between <image_urls> tags.
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

    if "<image_urls>" not in response:
        # 2. Extract image URLs from the response text
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

    else:
        # 2 Extract the string of list of image URLs between <image_urls> tags
        pattern = r"<image_urls>(.*?)</image_urls>"

        try:
            image_urls = re.search(pattern, response)
            if image_urls:
                # Convert the string of list of image URLs to a list
                image_urls = json.loads(image_urls.group(1).replace("'", '"'))
                for url in image_urls:
                    processed_parts.append(("image", url))
            else:
                logger.error("No image URLs found")

        except Exception as e:
            logger.error(f"Error extracting image URLs: {e}")

    return processed_parts


async def get_agent_input_from_message(
    message: Message,
    stream: bool,
    request_context: RequestContext,
) -> Input:
    """
    Converts a Message object into an Input object for the Agent.
    Handles email body extraction from S3 for email messages.

    Args:
        message (Message): The Message object to be converted.
        stream (bool): Whether the request is for streaming mode.
        request_context (RequestContext): The request context containing metadata about the request.

    Returns:
        Input: The Input object created from the Message, with history if available.
    """
    content = message.text.body if message.text else ""

    message_id = message.channel_info.get("messageId")
    logger.debug(
        f"processing input message: {message_id}, {message.channel}, {content}"
    )

    # Handle email body extraction from S3
    if message.channel == Channel.EMAIL and message.channel_info.get("messageId"):
        message_id = message.channel_info["messageId"]
        logger.info(f"Extracting email body for message ID: {message_id}")
        content = await _extract_email_body_from_s3(message_id)

    input_obj = Input(
        content=content,
        context=message.context,
        channel=message.channel,
        sender_identifier=message.sender_identifier,
        stream=stream,
        request_context=request_context,
    )

    return input_obj


async def _extract_email_body_from_s3(message_id: str) -> str:
    """
    Extract email body content from S3 based on message ID.

    Args:
        message_id (str): S3 message identifier or S3 URI

    Returns:
        str: Extracted email body content
    """
    try:
        # Get S3 bucket from environment variable or use default
        bucket_name = os.environ.get("SES_S3_BUCKET", "lat-pal-mono-bucket")

        # Create S3 client
        s3_client = boto3.client("s3")

        # Email is stored in emails folder with message ID as filename
        s3_key = f"emails/{message_id}"

        logger.debug(
            f"Extracting email body from S3: bucket={bucket_name}, key={s3_key}"
        )

        # Retrieve email from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        raw_email = response["Body"].read()

        # Parse email
        email_message = email.message_from_bytes(raw_email, policy=policy.default)

        # Extract text content
        email_body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    email_body = part.get_content()
                    break
                elif part.get_content_type() == "text/html" and not email_body:
                    # Fallback to HTML if no plain text found
                    email_body = part.get_content()
        else:
            email_body = email_message.get_content()

        extracted_body = email_body.strip() if email_body else ""

        # Create preview of body content for logging
        if extracted_body:
            if len(extracted_body) > 100:
                body_preview = f"{extracted_body[:50]}...{extracted_body[-50:]}"
            else:
                body_preview = extracted_body
        else:
            body_preview = "(empty)"

        logger.debug(
            f"Successfully extracted email body from S3 for message_id {message_id}. "
            f"Body length: {len(extracted_body)} characters. "
            f"Preview: {body_preview}"
        )
        return extracted_body

    except Exception as e:
        logger.error(
            f"Failed to extract email body from S3 for message_id {message_id}: {str(e)}"
        )
        # Return original message_id as fallback
        return message_id


def get_messages_from_agent_output(
    output: Output,
    input_message: Message,
    metadata: Metadata,
) -> List[Message]:
    """
    Converts an Output object from the Agent into a Message object.

    Args:
        output (Output): The Output object to be converted.
        input_message (Message): The original input message to derive response message properties from.
        metadata (Metadata): The metadata to attach to the response message(s).

    Returns:
        List[Message]: The Message object created from the Output.
    """
    msg_text = f"{output.content}"
    response_messages = []

    # Check if metadata exists in the input message, if not log an error
    if not input_message.metadata:
        logger.error("Metadata is missing in the input message")
        return response_messages

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
            channel_info=input_message.channel_info,
            text=TextObject(body=voice_msg_text),
            metadata=metadata,
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
            channel_info=input_message.channel_info,
            text=TextObject(body=msg_text),
            metadata=metadata,
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
                msg_content = remove_image_links(msg_content)
                # msg_content = strip_markdown_content(msg_content)
                response_message_text = Message(
                    author_type=AuthorType.AGENT,
                    sender_identifier=input_message.recipient_identifier,
                    recipient_identifier=input_message.sender_identifier,
                    channel=input_message.channel,
                    broker=input_message.broker,
                    channel_info=input_message.channel_info,
                    text=TextObject(body=msg_content),
                    metadata=metadata,
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
                    channel_info=input_message.channel_info,
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
            channel_info=input_message.channel_info,
            text=TextObject(body=msg_text),
            metadata=metadata,
            extras=Extras(
                escalated=output.escalated,
                closing_conversation=output.closing_conversation,
            ),
        )
        response_messages.append(response_message)

    return response_messages
