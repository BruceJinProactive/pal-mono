"""Tests for conversation endpoints."""

import datetime
import math
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.admin._conversation import (
    list_conversation_messages,
    lookup_conversation_account,
)
from api.routes.admin._utils import SortOrder
from api.schemas.admin.conversation import Message as SchemaMessage
from services.auth_types import UserRole


def _make_message(body: dict) -> MagicMock:
    """Create a mock db.Message with the given body dict."""
    msg = MagicMock()
    msg.body = body
    msg.id = uuid.uuid4()
    msg.conversation_id = uuid.uuid4()
    msg.created_at = "2026-04-21T00:00:00Z"
    return msg


def _make_schema_message(**overrides) -> SchemaMessage:
    """Create a valid Pydantic Message for build_message return values."""
    defaults = {
        "id": uuid.uuid4(),
        "content": None,
        "type": None,
        "channel": None,
        "author_type": None,
        "metadata": None,
        "channel_info": None,
        "sender_identifier": None,
        "recipient_identifier": None,
        "escalated": False,
        "sent_at": None,
        "created_at": datetime.datetime(2026, 4, 21, tzinfo=datetime.timezone.utc),
        "conversation_id": uuid.uuid4(),
        "media": None,
    }
    defaults.update(overrides)
    return SchemaMessage(**defaults)


def _make_context() -> MagicMock:
    context = MagicMock()
    context.email = "admin@test.com"
    context.username = str(uuid.uuid4())
    return context


class TestListConversationMessagesFiltering:
    """Verify that non-displayable messages are excluded from pagination."""

    @pytest.fixture
    def conversation(self):
        conv = MagicMock()
        conv.id = uuid.uuid4()
        conv.user.account.id = uuid.uuid4()
        conv.user.account.name = "test-account"
        return conv

    @pytest.fixture
    def base_mocks(self, conversation):
        with (
            patch("api.routes.admin._conversation.admin_service") as mock_admin,
            patch("api.routes.admin._conversation._builder") as mock_builder,
        ):
            mock_admin.get_conversation_by_id.return_value = conversation
            mock_builder.build_message.side_effect = lambda msg: _make_schema_message()
            yield mock_admin, mock_builder

    @pytest.mark.asyncio
    async def test_filters_out_empty_messages(self, conversation, base_mocks):
        mock_admin, _ = base_mocks

        displayable = _make_message(
            {"text": {"body": "Hello!"}, "author_type": "agent"}
        )
        empty = _make_message({})
        null_text = _make_message({"text": {}})
        null_body = _make_message({"text": {"body": None}})

        mock_admin.get_conversation_messages.return_value = [
            empty,
            null_text,
            displayable,
            null_body,
        ]

        result = await list_conversation_messages(
            account_name="test-account",
            conversation_id=conversation.id,
            page=1,
            page_size=10,
            sort_order=SortOrder.asc,
            context=_make_context(),
            session=MagicMock(),
        )

        assert result.total_messages == 1
        assert result.total_pages == 1
        assert len(result.messages) == 1

    @pytest.mark.asyncio
    async def test_filters_out_whitespace_only_messages(self, conversation, base_mocks):
        mock_admin, _ = base_mocks

        displayable = _make_message({"text": {"body": "Real content"}})
        whitespace = _make_message({"text": {"body": "   "}})
        newlines = _make_message({"text": {"body": "\n\t  "}})

        mock_admin.get_conversation_messages.return_value = [
            whitespace,
            displayable,
            newlines,
        ]

        result = await list_conversation_messages(
            account_name="test-account",
            conversation_id=conversation.id,
            page=1,
            page_size=10,
            sort_order=SortOrder.asc,
            context=_make_context(),
            session=MagicMock(),
        )

        assert result.total_messages == 1
        assert result.total_pages == 1

    @pytest.mark.asyncio
    async def test_keeps_media_messages(self, conversation, base_mocks):
        mock_admin, _ = base_mocks

        media_msg = _make_message({"media": {"url": "https://example.com/img.png"}})
        empty = _make_message({})

        mock_admin.get_conversation_messages.return_value = [empty, media_msg]

        result = await list_conversation_messages(
            account_name="test-account",
            conversation_id=conversation.id,
            page=1,
            page_size=10,
            sort_order=SortOrder.asc,
            context=_make_context(),
            session=MagicMock(),
        )

        assert result.total_messages == 1
        assert len(result.messages) == 1

    @pytest.mark.asyncio
    async def test_pagination_uses_filtered_count(self, conversation, base_mocks):
        mock_admin, _ = base_mocks

        # 5 displayable + 20 empty = 25 total raw messages
        displayable = [_make_message({"text": {"body": f"msg {i}"}}) for i in range(5)]
        empty = [_make_message({}) for _ in range(20)]

        mock_admin.get_conversation_messages.return_value = empty + displayable

        result = await list_conversation_messages(
            account_name="test-account",
            conversation_id=conversation.id,
            page=1,
            page_size=10,
            sort_order=SortOrder.asc,
            context=_make_context(),
            session=MagicMock(),
        )

        # Should be 5 displayable, not 25
        assert result.total_messages == 5
        assert result.total_pages == math.ceil(5 / 10)

    @pytest.mark.asyncio
    async def test_all_empty_returns_zero_pages(self, conversation, base_mocks):
        mock_admin, _ = base_mocks

        mock_admin.get_conversation_messages.return_value = [
            _make_message({}),
            _make_message({"text": {}}),
            _make_message({"text": {"body": None}}),
            _make_message({"text": {"body": "  "}}),
        ]

        result = await list_conversation_messages(
            account_name="test-account",
            conversation_id=conversation.id,
            page=1,
            page_size=10,
            sort_order=SortOrder.asc,
            context=_make_context(),
            session=MagicMock(),
        )

        assert result.total_messages == 0
        assert result.total_pages == 0
        assert len(result.messages) == 0


class TestLookupConversationAccount:
    """Tests for the conversation account lookup endpoint."""

    @pytest.fixture
    def conversation(self) -> MagicMock:
        conv = MagicMock()
        conv.id = uuid.uuid4()
        conv.user.account.id = uuid.uuid4()
        conv.user.account.name = "target-account"
        return conv

    @pytest.fixture
    def context(self) -> MagicMock:
        ctx = MagicMock()
        ctx.email = "user@test.com"
        ctx.username = str(uuid.uuid4())
        ctx.role = UserRole.AccountManager
        return ctx

    @pytest.mark.asyncio
    async def test_returns_account_name_when_user_has_access(
        self, conversation: MagicMock, context: MagicMock
    ) -> None:
        with (
            patch("api.routes.admin._conversation.admin_service") as mock_admin,
            patch("api.routes.admin._conversation.check_permission") as mock_check,
        ):
            mock_admin.get_conversation_by_id.return_value = conversation
            mock_check.return_value = True

            result = await lookup_conversation_account(
                conversation_id=conversation.id,
                context=context,
                session=MagicMock(),
            )

            assert result.account_name == "target-account"
            mock_check.assert_called_once_with(
                user_id=uuid.UUID(context.username),
                resource_id="accounts/target-account",
                permission_name="account.read",
                session=mock_admin.get_conversation_by_id.call_args[0][0],
                user_role=UserRole.AccountManager.value,
            )

    @pytest.mark.asyncio
    async def test_raises_404_when_conversation_not_found(
        self, context: MagicMock
    ) -> None:
        with patch("api.routes.admin._conversation.admin_service") as mock_admin:
            mock_admin.get_conversation_by_id.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await lookup_conversation_account(
                    conversation_id=uuid.uuid4(),
                    context=context,
                    session=MagicMock(),
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_404_when_user_lacks_permission(
        self, conversation: MagicMock, context: MagicMock
    ) -> None:
        with (
            patch("api.routes.admin._conversation.admin_service") as mock_admin,
            patch("api.routes.admin._conversation.check_permission") as mock_check,
        ):
            mock_admin.get_conversation_by_id.return_value = conversation
            mock_check.return_value = False

            with pytest.raises(HTTPException) as exc_info:
                await lookup_conversation_account(
                    conversation_id=conversation.id,
                    context=context,
                    session=MagicMock(),
                )

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_user_gets_access(self, conversation: MagicMock) -> None:
        admin_context = MagicMock()
        admin_context.email = "admin@palona.ai"
        admin_context.username = str(uuid.uuid4())
        admin_context.role = UserRole.Admin

        with (
            patch("api.routes.admin._conversation.admin_service") as mock_admin,
            patch("api.routes.admin._conversation.check_permission") as mock_check,
        ):
            mock_admin.get_conversation_by_id.return_value = conversation
            mock_check.return_value = (
                True  # check_permission returns True for Admin role
            )

            result = await lookup_conversation_account(
                conversation_id=conversation.id,
                context=admin_context,
                session=MagicMock(),
            )

            assert result.account_name == "target-account"
