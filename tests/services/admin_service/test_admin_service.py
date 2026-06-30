from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, call
from uuid import UUID, uuid4

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

import db
from services.admin_service._implementation import (
    _include_conversation_preview,
    get_conversation_messages,
    get_conversation_order_details,
    get_conversation_order_display_info,
    list_conversations_in_account,
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


def test_list_conversations_in_account_includes_order_number(mocker):
    """
    Test list_conversations_in_account attaches the latest order number.

    Expected result: preview carries the external order identifier for display.
    """
    account_id = uuid4()
    conversation_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    conversation = MagicMock()
    conversation.id = conversation_id
    latest_order = SimpleNamespace(order_id="ORD-123")

    message_repository = MagicMock()
    message_repository.get_last_user_message_by_conversation.return_value = None
    message_repository.get_last_message_by_conversation.return_value = MagicMock()
    message_repository.get_message_count_by_conversation.return_value = 3

    conversation_repository = MagicMock()
    conversation_repository.get_conversation_ids_by_user_ids.return_value = [
        conversation_id
    ]
    conversation_repository.get_paginated_sessions_by_ids.return_value = (
        1,
        [conversation],
    )

    order_repository = MagicMock()
    order_repository.get_latest_orders_by_conversation_ids.return_value = {
        conversation_id: latest_order
    }

    mocker.patch(
        "services.admin_service._implementation.user_service.get_users_by_account_id",
        return_value=[user],
    )
    mocker.patch(
        "services.admin_service._implementation.db.MessageRepository",
        return_value=message_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.ConversationRepository",
        return_value=conversation_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    total, previews = list_conversations_in_account(
        account_id=account_id,
        keyword="",
        channel=None,
        language=None,
        purpose=None,
        ended_reason=None,
        customer_converted=None,
        project_id=None,
        start_date=None,
        end_date=datetime.now(timezone.utc),
        page=1,
        page_size=10,
        escalated=False,
        hide_testing_sessions=True,
        db_session=mock_session,
    )

    assert total == 1
    assert previews[0].order_number == "ORD-123"
    assert previews[0].has_order is True
    order_repository.get_latest_orders_by_conversation_ids.assert_called_once_with(
        [conversation_id]
    )


def test_list_conversations_in_account_hides_placeholder_order_number(mocker) -> None:
    """
    Test list_conversations_in_account hides placeholder order IDs.

    Expected result: preview still indicates an order exists.
    """
    account_id = uuid4()
    conversation_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    conversation = MagicMock()
    conversation.id = conversation_id
    latest_order = SimpleNamespace(order_id="0")

    message_repository = MagicMock()
    message_repository.get_last_user_message_by_conversation.return_value = None
    message_repository.get_last_message_by_conversation.return_value = MagicMock()
    message_repository.get_message_count_by_conversation.return_value = 3

    conversation_repository = MagicMock()
    conversation_repository.get_conversation_ids_by_user_ids.return_value = [
        conversation_id
    ]
    conversation_repository.get_paginated_sessions_by_ids.return_value = (
        1,
        [conversation],
    )

    order_repository = MagicMock()
    order_repository.get_latest_orders_by_conversation_ids.return_value = {
        conversation_id: latest_order
    }

    mocker.patch(
        "services.admin_service._implementation.user_service.get_users_by_account_id",
        return_value=[user],
    )
    mocker.patch(
        "services.admin_service._implementation.db.MessageRepository",
        return_value=message_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.ConversationRepository",
        return_value=conversation_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    total, previews = list_conversations_in_account(
        account_id=account_id,
        keyword="",
        channel=None,
        language=None,
        purpose=None,
        ended_reason=None,
        customer_converted=None,
        project_id=None,
        start_date=None,
        end_date=datetime.now(timezone.utc),
        page=1,
        page_size=10,
        escalated=False,
        hide_testing_sessions=True,
        db_session=mock_session,
    )

    assert total == 1
    assert previews[0].order_number is None
    assert previews[0].has_order is True
    message_repository.get_messages_by_conversation.assert_not_called()


def test_list_conversations_in_account_pins_selected_conversation(
    mocker: MockerFixture,
) -> None:
    """
    Test list_conversations_in_account pins a requested conversation.

    Expected result: a deep-linked conversation appears first even when it is not
    part of the current paginated result set.
    """
    account_id = uuid4()
    selected_conversation_id = uuid4()
    recent_conversation_id = uuid4()
    user = SimpleNamespace(id=uuid4())

    selected_conversation = MagicMock()
    selected_conversation.id = selected_conversation_id
    selected_conversation.user.account_id = account_id

    recent_conversation = MagicMock()
    recent_conversation.id = recent_conversation_id

    message_repository = MagicMock()
    message_repository.get_last_user_message_by_conversation.return_value = None
    message_repository.get_last_message_by_conversation.return_value = MagicMock()
    message_repository.get_message_count_by_conversation.return_value = 3

    conversation_repository = MagicMock()
    conversation_repository.get_conversation_ids_by_user_ids.return_value = [
        recent_conversation_id
    ]
    conversation_repository.get_paginated_sessions_by_ids.return_value = (
        1,
        [recent_conversation],
    )
    conversation_repository.get_conversation_by_id.return_value = selected_conversation

    order_repository = MagicMock()
    order_repository.get_latest_orders_by_conversation_ids.return_value = {}

    mocker.patch(
        "services.admin_service._implementation.user_service.get_users_by_account_id",
        return_value=[user],
    )
    mocker.patch(
        "services.admin_service._implementation.db.MessageRepository",
        return_value=message_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.ConversationRepository",
        return_value=conversation_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    total, previews = list_conversations_in_account(
        account_id=account_id,
        keyword="",
        channel=None,
        language=None,
        purpose=None,
        ended_reason=None,
        customer_converted=None,
        project_id=None,
        start_date=None,
        end_date=datetime.now(timezone.utc),
        page=1,
        page_size=10,
        escalated=False,
        hide_testing_sessions=True,
        db_session=mock_session,
        conversation_id=selected_conversation_id,
    )

    assert total == 2
    assert [preview.conversation.id for preview in previews] == [
        selected_conversation_id,
        recent_conversation_id,
    ]
    order_repository.get_latest_orders_by_conversation_ids.assert_called_once_with(
        [selected_conversation_id, recent_conversation_id]
    )


def test_list_conversations_in_account_does_not_reorder_visible_selection(
    mocker: MockerFixture,
) -> None:
    """
    Test list_conversations_in_account leaves visible selected conversations in place.

    Expected result: selecting a conversation already on the first page does not
    pin it to the top and reshuffle the list.
    """
    account_id = uuid4()
    recent_conversation_id = uuid4()
    selected_conversation_id = uuid4()
    user = SimpleNamespace(id=uuid4())

    recent_conversation = MagicMock()
    recent_conversation.id = recent_conversation_id

    selected_conversation = MagicMock()
    selected_conversation.id = selected_conversation_id
    selected_conversation.user.account_id = account_id

    message_repository = MagicMock()
    message_repository.get_last_user_message_by_conversation.return_value = None
    message_repository.get_last_message_by_conversation.return_value = MagicMock()
    message_repository.get_message_count_by_conversation.return_value = 3

    conversation_repository = MagicMock()
    conversation_repository.get_conversation_ids_by_user_ids.return_value = [
        recent_conversation_id,
        selected_conversation_id,
    ]
    conversation_repository.get_paginated_sessions_by_ids.return_value = (
        2,
        [recent_conversation, selected_conversation],
    )
    conversation_repository.get_conversation_by_id.return_value = selected_conversation

    order_repository = MagicMock()
    order_repository.get_latest_orders_by_conversation_ids.return_value = {}

    mocker.patch(
        "services.admin_service._implementation.user_service.get_users_by_account_id",
        return_value=[user],
    )
    mocker.patch(
        "services.admin_service._implementation.db.MessageRepository",
        return_value=message_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.ConversationRepository",
        return_value=conversation_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    total, previews = list_conversations_in_account(
        account_id=account_id,
        keyword="",
        channel=None,
        language=None,
        purpose=None,
        ended_reason=None,
        customer_converted=None,
        project_id=None,
        start_date=None,
        end_date=datetime.now(timezone.utc),
        page=1,
        page_size=10,
        escalated=False,
        hide_testing_sessions=True,
        db_session=mock_session,
        conversation_id=selected_conversation_id,
    )

    assert total == 2
    assert [preview.conversation.id for preview in previews] == [
        recent_conversation_id,
        selected_conversation_id,
    ]
    conversation_repository.get_paginated_sessions_by_ids.assert_called_once_with(
        [recent_conversation_id, selected_conversation_id],
        offset=0,
        limit=10,
    )
    order_repository.get_latest_orders_by_conversation_ids.assert_called_once_with(
        [recent_conversation_id, selected_conversation_id]
    )


def test_list_conversations_in_account_uses_actual_page_for_pin_decision(
    mocker: MockerFixture,
) -> None:
    """
    Test list_conversations_in_account checks the fetched first page before pinning.

    Expected result: a deep-linked conversation is pinned when the raw ID list
    position suggests it is visible but the repository-ordered first page excludes it.
    """
    account_id = uuid4()
    selected_conversation_id = uuid4()
    recent_conversation_id = uuid4()
    other_conversation_id = uuid4()
    user = SimpleNamespace(id=uuid4())

    selected_conversation = MagicMock()
    selected_conversation.id = selected_conversation_id
    selected_conversation.user.account_id = account_id

    recent_conversation = MagicMock()
    recent_conversation.id = recent_conversation_id

    other_conversation = MagicMock()
    other_conversation.id = other_conversation_id

    message_repository = MagicMock()
    message_repository.get_last_user_message_by_conversation.return_value = None
    message_repository.get_last_message_by_conversation.return_value = MagicMock()
    message_repository.get_message_count_by_conversation.return_value = 3

    conversation_repository = MagicMock()
    conversation_repository.get_conversation_ids_by_user_ids.return_value = [
        selected_conversation_id,
        recent_conversation_id,
        other_conversation_id,
    ]
    conversation_repository.get_paginated_sessions_by_ids.side_effect = [
        (3, [recent_conversation, other_conversation]),
        (2, [recent_conversation]),
    ]
    conversation_repository.get_conversation_by_id.return_value = selected_conversation

    order_repository = MagicMock()
    order_repository.get_latest_orders_by_conversation_ids.return_value = {}

    mocker.patch(
        "services.admin_service._implementation.user_service.get_users_by_account_id",
        return_value=[user],
    )
    mocker.patch(
        "services.admin_service._implementation.db.MessageRepository",
        return_value=message_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.ConversationRepository",
        return_value=conversation_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    total, previews = list_conversations_in_account(
        account_id=account_id,
        keyword="",
        channel=None,
        language=None,
        purpose=None,
        ended_reason=None,
        customer_converted=None,
        project_id=None,
        start_date=None,
        end_date=datetime.now(timezone.utc),
        page=1,
        page_size=2,
        escalated=False,
        hide_testing_sessions=True,
        db_session=mock_session,
        conversation_id=selected_conversation_id,
    )

    assert total == 3
    assert [preview.conversation.id for preview in previews] == [
        selected_conversation_id,
        recent_conversation_id,
    ]
    assert conversation_repository.get_paginated_sessions_by_ids.call_args_list == [
        call(
            [selected_conversation_id, recent_conversation_id, other_conversation_id],
            offset=0,
            limit=2,
        ),
        call(
            [recent_conversation_id, other_conversation_id],
            offset=0,
            limit=1,
        ),
    ]
    order_repository.get_latest_orders_by_conversation_ids.assert_called_once_with(
        [selected_conversation_id, recent_conversation_id]
    )


def test_list_conversations_in_account_does_not_repin_after_first_page(
    mocker: MockerFixture,
) -> None:
    """
    Test list_conversations_in_account only pins on the first page.

    Expected result: later pages keep normal pagination so browsing through
    visible conversations does not reshuffle the list.
    """
    account_id = uuid4()
    selected_conversation_id = uuid4()
    first_page_conversation_ids = [uuid4() for _ in range(10)]
    page_two_conversation_id = uuid4()
    user = SimpleNamespace(id=uuid4())

    selected_conversation = MagicMock()
    selected_conversation.id = selected_conversation_id
    selected_conversation.user.account_id = account_id

    page_two_conversation = MagicMock()
    page_two_conversation.id = page_two_conversation_id

    message_repository = MagicMock()
    message_repository.get_last_user_message_by_conversation.return_value = None
    message_repository.get_last_message_by_conversation.return_value = MagicMock()
    message_repository.get_message_count_by_conversation.return_value = 3

    conversation_repository = MagicMock()
    conversation_repository.get_conversation_ids_by_user_ids.return_value = [
        *first_page_conversation_ids,
        selected_conversation_id,
        page_two_conversation_id,
    ]
    conversation_repository.get_paginated_sessions_by_ids.return_value = (
        12,
        [selected_conversation, page_two_conversation],
    )
    conversation_repository.get_conversation_by_id.return_value = selected_conversation

    order_repository = MagicMock()
    order_repository.get_latest_orders_by_conversation_ids.return_value = {}

    mocker.patch(
        "services.admin_service._implementation.user_service.get_users_by_account_id",
        return_value=[user],
    )
    mocker.patch(
        "services.admin_service._implementation.db.MessageRepository",
        return_value=message_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.ConversationRepository",
        return_value=conversation_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    total, previews = list_conversations_in_account(
        account_id=account_id,
        keyword="",
        channel=None,
        language=None,
        purpose=None,
        ended_reason=None,
        customer_converted=None,
        project_id=None,
        start_date=None,
        end_date=datetime.now(timezone.utc),
        page=2,
        page_size=10,
        escalated=False,
        hide_testing_sessions=True,
        db_session=mock_session,
        conversation_id=selected_conversation_id,
    )

    assert total == 12
    assert [preview.conversation.id for preview in previews] == [
        selected_conversation_id,
        page_two_conversation_id,
    ]
    conversation_repository.get_paginated_sessions_by_ids.assert_called_once_with(
        [
            *first_page_conversation_ids,
            selected_conversation_id,
            page_two_conversation_id,
        ],
        offset=10,
        limit=10,
    )
    conversation_repository.get_conversation_by_id.assert_not_called()


def test_list_conversations_in_account_does_not_pin_wrong_account(
    mocker: MockerFixture,
) -> None:
    """
    Test list_conversations_in_account ignores selected conversations from other accounts.

    Expected result: account-scoped listing does not expose another account's conversation.
    """
    account_id = uuid4()
    selected_conversation_id = uuid4()
    recent_conversation_id = uuid4()
    user = SimpleNamespace(id=uuid4())

    selected_conversation = MagicMock()
    selected_conversation.id = selected_conversation_id
    selected_conversation.user.account_id = uuid4()

    recent_conversation = MagicMock()
    recent_conversation.id = recent_conversation_id

    message_repository = MagicMock()
    message_repository.get_last_user_message_by_conversation.return_value = None
    message_repository.get_last_message_by_conversation.return_value = MagicMock()
    message_repository.get_message_count_by_conversation.return_value = 3

    conversation_repository = MagicMock()
    conversation_repository.get_conversation_ids_by_user_ids.return_value = [
        recent_conversation_id
    ]
    conversation_repository.get_paginated_sessions_by_ids.return_value = (
        1,
        [recent_conversation],
    )
    conversation_repository.get_conversation_by_id.return_value = selected_conversation

    order_repository = MagicMock()
    order_repository.get_latest_orders_by_conversation_ids.return_value = {}

    mocker.patch(
        "services.admin_service._implementation.user_service.get_users_by_account_id",
        return_value=[user],
    )
    mocker.patch(
        "services.admin_service._implementation.db.MessageRepository",
        return_value=message_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.ConversationRepository",
        return_value=conversation_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    total, previews = list_conversations_in_account(
        account_id=account_id,
        keyword="",
        channel=None,
        language=None,
        purpose=None,
        ended_reason=None,
        customer_converted=None,
        project_id=None,
        start_date=None,
        end_date=datetime.now(timezone.utc),
        page=1,
        page_size=10,
        escalated=False,
        hide_testing_sessions=True,
        db_session=mock_session,
        conversation_id=selected_conversation_id,
    )

    assert total == 1
    assert [preview.conversation.id for preview in previews] == [recent_conversation_id]


def test_list_conversations_in_account_does_not_pin_wrong_project(
    mocker: MockerFixture,
) -> None:
    """
    Test list_conversations_in_account ignores selected conversations from other projects.

    Expected result: project-scoped listing does not pin a conversation from
    another store in the same account.
    """
    account_id = uuid4()
    selected_project_id = uuid4()
    other_project_id = uuid4()
    selected_conversation_id = uuid4()
    recent_conversation_id = uuid4()
    user = SimpleNamespace(id=uuid4())

    selected_conversation = MagicMock()
    selected_conversation.id = selected_conversation_id
    selected_conversation.project_id = other_project_id
    selected_conversation.user.account_id = account_id

    recent_conversation = MagicMock()
    recent_conversation.id = recent_conversation_id
    recent_conversation.project_id = selected_project_id

    message_repository = MagicMock()
    message_repository.get_last_user_message_by_conversation.return_value = None
    message_repository.get_last_message_by_conversation.return_value = MagicMock()
    message_repository.get_message_count_by_conversation.return_value = 3

    conversation_repository = MagicMock()
    conversation_repository.get_conversation_ids_by_user_ids.return_value = [
        recent_conversation_id
    ]
    conversation_repository.get_paginated_sessions_by_ids.return_value = (
        1,
        [recent_conversation],
    )
    conversation_repository.get_conversation_by_id.return_value = selected_conversation

    order_repository = MagicMock()
    order_repository.get_latest_orders_by_conversation_ids.return_value = {}

    mocker.patch(
        "services.admin_service._implementation.user_service.get_users_by_account_id",
        return_value=[user],
    )
    mocker.patch(
        "services.admin_service._implementation.db.MessageRepository",
        return_value=message_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.ConversationRepository",
        return_value=conversation_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    total, previews = list_conversations_in_account(
        account_id=account_id,
        keyword="",
        channel=None,
        language=None,
        purpose=None,
        ended_reason=None,
        customer_converted=None,
        project_id=selected_project_id,
        start_date=None,
        end_date=datetime.now(timezone.utc),
        page=1,
        page_size=10,
        escalated=False,
        hide_testing_sessions=True,
        db_session=mock_session,
        conversation_id=selected_conversation_id,
    )

    assert total == 1
    assert [preview.conversation.id for preview in previews] == [recent_conversation_id]
    order_repository.get_latest_orders_by_conversation_ids.assert_called_once_with(
        [recent_conversation_id]
    )


def test_list_conversations_in_account_filters_by_order_presence(mocker) -> None:
    """
    Test list_conversations_in_account passes the order-presence filter to storage.

    Expected result: repository-level filtering controls pagination and totals.
    """
    account_id = uuid4()
    user = SimpleNamespace(id=uuid4())

    message_repository = MagicMock()
    conversation_repository = MagicMock()
    conversation_repository.get_conversation_ids_by_user_ids.return_value = []
    conversation_repository.get_paginated_sessions_by_ids.return_value = (0, [])

    order_repository = MagicMock()
    order_repository.get_latest_orders_by_conversation_ids.return_value = {}

    mocker.patch(
        "services.admin_service._implementation.user_service.get_users_by_account_id",
        return_value=[user],
    )
    mocker.patch(
        "services.admin_service._implementation.db.MessageRepository",
        return_value=message_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.ConversationRepository",
        return_value=conversation_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    total, previews = list_conversations_in_account(
        account_id=account_id,
        keyword="",
        channel=None,
        language=None,
        purpose=None,
        ended_reason=None,
        customer_converted=None,
        project_id=None,
        start_date=None,
        end_date=datetime.now(timezone.utc),
        page=1,
        page_size=10,
        escalated=False,
        hide_testing_sessions=True,
        db_session=mock_session,
        has_order=True,
    )

    assert total == 0
    assert previews == []
    conversation_repository.get_conversation_ids_by_user_ids.assert_called_once_with(
        [user.id],
        None,
        ANY,
        None,
        True,
        None,
        None,
        None,
        None,
        has_order=True,
        order_filter=None,
    )


def test_list_conversations_in_account_filters_by_order_display_state(mocker) -> None:
    """
    Test list_conversations_in_account passes the order display-state filter.

    Expected result: repository-level filtering controls pagination and totals.
    """
    account_id = uuid4()
    user = SimpleNamespace(id=uuid4())

    message_repository = MagicMock()
    conversation_repository = MagicMock()
    conversation_repository.get_conversation_ids_by_user_ids.return_value = []
    conversation_repository.get_paginated_sessions_by_ids.return_value = (0, [])

    order_repository = MagicMock()
    order_repository.get_latest_orders_by_conversation_ids.return_value = {}

    mocker.patch(
        "services.admin_service._implementation.user_service.get_users_by_account_id",
        return_value=[user],
    )
    mocker.patch(
        "services.admin_service._implementation.db.MessageRepository",
        return_value=message_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.ConversationRepository",
        return_value=conversation_repository,
    )
    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    total, previews = list_conversations_in_account(
        account_id=account_id,
        keyword="",
        channel=None,
        language=None,
        purpose=None,
        ended_reason=None,
        customer_converted=None,
        project_id=None,
        start_date=None,
        end_date=datetime.now(timezone.utc),
        page=1,
        page_size=10,
        escalated=False,
        hide_testing_sessions=True,
        db_session=mock_session,
        order_filter="paid",
    )

    assert total == 0
    assert previews == []
    conversation_repository.get_conversation_ids_by_user_ids.assert_called_once_with(
        [user.id],
        None,
        ANY,
        None,
        True,
        None,
        None,
        None,
        None,
        has_order=None,
        order_filter="paid",
    )


def test_get_conversation_order_display_info_hides_placeholder_id(mocker) -> None:
    """
    Test get_conversation_order_display_info does not expose placeholder order IDs.

    Expected result: the admin API returns has_order for frontend display.
    """
    conversation_id = uuid4()
    order_repository = MagicMock()
    order_repository.get_latest_order_by_conversation_id.return_value = SimpleNamespace(
        order_id="0"
    )

    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    result = get_conversation_order_display_info(mock_session, conversation_id)

    assert result.order_number is None
    assert result.has_order is True


def test_get_conversation_order_details_delegates_to_repository(mocker) -> None:
    """
    Test get_conversation_order_details fetches the latest order detail projection.

    Expected result: the service returns the repository detail payload unchanged.
    """
    conversation_id = uuid4()
    expected_order = SimpleNamespace(id=uuid4(), conversation_id=conversation_id)
    order_repository = MagicMock()
    order_repository.get_latest_order_details_by_conversation_id.return_value = (
        expected_order
    )

    mocker.patch(
        "services.admin_service._implementation.db.OrderRepository",
        return_value=order_repository,
    )

    result = get_conversation_order_details(mock_session, conversation_id)

    assert result is expected_order
    order_repository.get_latest_order_details_by_conversation_id.assert_called_once_with(
        conversation_id
    )
