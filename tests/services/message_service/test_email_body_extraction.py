import asyncio
from collections.abc import Iterator
from email.message import EmailMessage
from email.message import Message as ParsedMessage
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ReadTimeoutError

from api.schemas.chat.message import AuthorType, Message, TextObject
from db.tables.types import Channel
from services.message_service import _utils
from utils.request_context import RequestContext


def _s3_client_with_raw_email(raw_email: bytes) -> MagicMock:
    s3_client = MagicMock()
    s3_client.get_object.return_value = {"Body": BytesIO(raw_email)}
    return s3_client


@pytest.mark.asyncio
async def test_extract_email_body_from_s3_uses_text_plain_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_email = (
        b"Subject: Order question\r\n"
        b"Content-Type: multipart/alternative; boundary=test-boundary\r\n"
        b"\r\n"
        b"--test-boundary\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"This is the real email body.\r\n"
        b"--test-boundary\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"\r\n"
        b"<html><body>This is the HTML body.</body></html>\r\n"
        b"--test-boundary--\r\n"
    )
    s3_client = _s3_client_with_raw_email(raw_email)
    monkeypatch.setenv("SES_S3_BUCKET", "email-bucket")
    client_calls = []

    def fake_boto3_client(service_name: str, **kwargs: object) -> MagicMock:
        client_calls.append((service_name, kwargs))
        return s3_client

    monkeypatch.setattr(_utils.boto3, "client", fake_boto3_client)

    body = await _utils._extract_email_body_from_s3("ses-message-id")

    assert body == "This is the real email body."
    assert client_calls == [
        (
            "s3",
            {"config": _utils._EMAIL_S3_CLIENT_CONFIG},
        )
    ]
    assert getattr(_utils._EMAIL_S3_CLIENT_CONFIG, "connect_timeout") == 2
    assert getattr(_utils._EMAIL_S3_CLIENT_CONFIG, "read_timeout") == 3
    s3_client.get_object.assert_called_once_with(
        Bucket="email-bucket",
        Key="emails/ses-message-id",
    )


@pytest.mark.asyncio
async def test_extract_email_body_from_s3_supports_s3_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_email = (
        b"Subject: Order question\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Body from explicit S3 URI.\r\n"
    )
    s3_client = _s3_client_with_raw_email(raw_email)
    monkeypatch.setattr(
        _utils.boto3,
        "client",
        lambda service_name, **kwargs: s3_client,
    )

    body = await _utils._extract_email_body_from_s3(
        "s3://custom-bucket/inbound/email-id"
    )

    assert body == "Body from explicit S3 URI."
    s3_client.get_object.assert_called_once_with(
        Bucket="custom-bucket",
        Key="inbound/email-id",
    )


@pytest.mark.asyncio
async def test_extract_email_body_from_s3_does_not_fallback_to_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s3_client = MagicMock()
    s3_client.get_object.side_effect = RuntimeError("S3 unavailable")
    monkeypatch.setattr(
        _utils.boto3,
        "client",
        lambda service_name, **kwargs: s3_client,
    )

    body = await _utils._extract_email_body_from_s3(
        "Email title that must not become body",
        fallback_body="Original fallback body",
    )

    assert body == "Original fallback body"


@pytest.mark.asyncio
async def test_extract_email_body_from_s3_returns_fallback_on_read_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s3_client = MagicMock()
    s3_client.get_object.side_effect = ReadTimeoutError(endpoint_url="s3://bucket/key")
    monkeypatch.setattr(
        _utils.boto3,
        "client",
        lambda service_name, **kwargs: s3_client,
    )

    body = await _utils._extract_email_body_from_s3(
        "ses-message-id",
        fallback_body="Original email text",
    )

    assert body == "Original email text"


@pytest.mark.asyncio
async def test_get_agent_input_keeps_body_when_s3_extraction_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_extract_email_body(
        message_id: str,
        fallback_body: str = "",
    ) -> str:
        await asyncio.sleep(1)
        return f"{message_id}:{fallback_body}"

    monkeypatch.setattr(_utils, "EMAIL_BODY_EXTRACTION_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(_utils, "_extract_email_body_from_s3", slow_extract_email_body)

    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="customer@example.com",
        recipient_identifier="store@example.com",
        channel=Channel.EMAIL,
        channel_info={"messageId": "ses-message-id"},
        text=TextObject(body="Original fallback body"),
    )

    agent_input = await _utils.get_agent_input_from_message(
        message=message,
        stream=False,
        request_context=RequestContext(),
    )

    assert agent_input.content == "Original fallback body"


@pytest.mark.asyncio
async def test_extract_email_body_from_s3_returns_fallback_for_non_email_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_utils, "_read_raw_email_from_s3", lambda *args: b"raw")
    monkeypatch.setattr(
        _utils.email,
        "message_from_bytes",
        lambda *args, **kwargs: ParsedMessage(),
    )

    body = await _utils._extract_email_body_from_s3(
        "ses-message-id",
        fallback_body="Original fallback body",
    )

    assert body == "Original fallback body"


@pytest.mark.asyncio
async def test_extract_email_body_from_s3_skips_non_email_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_message = EmailMessage()
    text_part = EmailMessage()
    text_part.set_content("Body after skipped part")

    def walk_with_unexpected_part() -> Iterator[object]:
        return iter([ParsedMessage(), text_part])

    setattr(root_message, "is_multipart", lambda: True)
    setattr(root_message, "walk", walk_with_unexpected_part)

    monkeypatch.setattr(_utils, "_read_raw_email_from_s3", lambda *args: b"raw")
    monkeypatch.setattr(
        _utils.email,
        "message_from_bytes",
        lambda *args, **kwargs: root_message,
    )

    body = await _utils._extract_email_body_from_s3("ses-message-id")

    assert body == "Body after skipped part"


@pytest.mark.asyncio
async def test_email_agent_input_keeps_body_without_message_id() -> None:
    message = Message(
        author_type=AuthorType.USER,
        sender_identifier="customer@example.com",
        recipient_identifier="store@example.com",
        channel=Channel.EMAIL,
        channel_info={},
        text=TextObject(body="Re: Message from Palona"),
    )

    agent_input = await _utils.get_agent_input_from_message(
        message=message,
        stream=False,
        request_context=RequestContext(),
    )

    assert agent_input.content == "Re: Message from Palona"
