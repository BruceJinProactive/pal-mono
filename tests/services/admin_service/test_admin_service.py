from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

import db
from services.admin_service._implementation import (
    _include_conversation_preview,
    get_conversation_messages,
)

mock_session = MagicMock(spec=Session)
mock_account_uuid = UUID("12345678-1234-5678-1234-567812345678")
mock_conversation_uuid = MagicMock(spec=UUID)


def test_include_conversation_preview_no_limit(mocker):
    """
    Test _include_conversation_preview without a limit

    Expected result: accept
    """
    assert _include_conversation_preview(mocker.Mock(), 0)


def test_include_conversation_preview_within_limit(mocker):
    """
    Test _include_conversation_preview with a message with a creation time within the specified limit

    Expected result: accept
    """
    message_mock = mocker.Mock()
    message_mock.created_at = datetime.now(timezone.utc) - timedelta(minutes=4.9)
    assert _include_conversation_preview(message_mock, 5)


def test_include_conversation_preview_outside_limit(mocker):
    """
    Test _include_conversation_preview with a message with a creation time outside the specified limit

    Expected result: reject
    """
    message_mock = mocker.Mock()
    message_mock.created_at = datetime.now(timezone.utc) - timedelta(minutes=5.1)
    assert not _include_conversation_preview(message_mock, 5)


def test_get_conversation_messages_valid_user(mocker):
    """
    Test get_conversation_messages with a properly authorized user

    Expected result: desired messages are fetched
    """
    conversation_mock = mocker.Mock()
    conversation_mock.user_id = 2
    user_mock = mocker.Mock()
    user_mock.account_id = mock_account_uuid
    messages = ["mock_message1", "mock_message2"]

    mocker.patch.object(
        db.ConversationRepository,
        "get_conversation_by_id",
        return_value=conversation_mock,
    )
    mocker.patch.object(db.UserRepository, "get_user_by_id", return_value=user_mock)
    mocker.patch(
        "services.admin_service._implementation.get_messages_by_conversation",
        return_value=messages,
    )
    assert (
        get_conversation_messages(
            mock_session, mock_account_uuid, mock_conversation_uuid
        )
        == messages
    )


def test_get_conversation_messages_invalid_auth(mocker):
    """
    Test get_conversation_messages with a user that should not have access to those conversations

    Expected result: return error
    """
    conversation_mock = mocker.Mock()
    conversation_mock.user_id = 0
    user_mock = mocker.Mock()
    user_mock.account_id = 1

    mocker.patch.object(
        db.ConversationRepository,
        "get_conversation_by_id",
        return_value=conversation_mock,
    )
    mocker.patch.object(db.UserRepository, "get_user_by_id", return_value=user_mock)
    with pytest.raises(ValueError):
        get_conversation_messages(
            mock_session, mock_account_uuid, mock_conversation_uuid
        )
