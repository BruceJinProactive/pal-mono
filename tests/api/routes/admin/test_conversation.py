"""Tests for conversation endpoints."""

import datetime
import math
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes.admin import _builder
from api.routes.admin._conversation import (
    get_conversation_detail,
    list_account_conversations,
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


def _make_conversation_for_sender_identifier(
    channel_value: str | None,
    channel_identifiers: list[str] | None,
) -> MagicMock:
    conversation = MagicMock()
    conversation.user.channel_identifiers = channel_identifiers
    conversation.channel = (
        SimpleNamespace(value=channel_value) if channel_value else None
    )
    return conversation


def _make_builder_conversation(
    channel_value: str | None,
    channel_identifiers: list[str] | None,
) -> MagicMock:
    conversation = _make_conversation_for_sender_identifier(
        channel_value,
        channel_identifiers,
    )
    conversation.id = uuid.uuid4()
    conversation.status = SimpleNamespace(value="active")
    conversation.project_id = uuid.uuid4()
    conversation.created_at = datetime.datetime(
        2026, 4, 21, tzinfo=datetime.timezone.utc
    )
    conversation.purpose = None
    conversation.language = None
    conversation.ended_reason = None
    conversation.customer_converted = None
    conversation.transfer_purpose = None
    conversation.agent_fingerprint = None
    conversation.prompt_fingerprint = None

    conversation.user_id = uuid.uuid4()
    conversation.is_test = False
    conversation.vapi_control_url = None
    conversation.call_id = None
    conversation.updated_at = None
    return conversation


class TestConversationSenderIdentifier:
    """Verify admin conversation responses can expose caller identifiers."""

    def test_returns_none_when_user_has_no_channel_identifiers(self) -> None:
        conversation = _make_conversation_for_sender_identifier("voice", None)

        result = _builder._get_conversation_sender_identifier(conversation)

        assert result is None

    def test_prefers_identifier_matching_conversation_channel(self) -> None:
        conversation = _make_conversation_for_sender_identifier(
            "voice",
            ["sms:+15550000000", "voice:+15551112222"],
        )

        result = _builder._get_conversation_sender_identifier(conversation)

        assert result == "+15551112222"

    def test_falls_back_to_first_prefixed_identifier_without_channel_match(
        self,
    ) -> None:
        conversation = _make_conversation_for_sender_identifier(
            "voice",
            ["sms:+15550000000"],
        )

        result = _builder._get_conversation_sender_identifier(conversation)

        assert result == "+15550000000"

    def test_falls_back_to_prefixed_identifier_before_raw_identifier(self) -> None:
        conversation = _make_conversation_for_sender_identifier(
            "voice",
            ["customer-123", "phone:+15550000000"],
        )

        result = _builder._get_conversation_sender_identifier(conversation)

        assert result == "+15550000000"

    def test_falls_back_to_first_raw_identifier(self) -> None:
        conversation = _make_conversation_for_sender_identifier(
            None,
            ["customer-123"],
        )

        result = _builder._get_conversation_sender_identifier(conversation)

        assert result == "customer-123"

    def test_build_conversation_response_includes_sender_identifier(self) -> None:
        conversation = _make_builder_conversation("voice", ["voice:+15551112222"])

        result = _builder.build_conversation(
            conversation=conversation,
            message_count=1,
            last_message=None,
        )

        assert result.sender_identifier == "+15551112222"

    def test_build_conversation_response_includes_order_number(self) -> None:
        conversation = _make_builder_conversation("voice", ["voice:+15551112222"])

        result = _builder.build_conversation(
            conversation=conversation,
            message_count=1,
            last_message=None,
            order_number="ORD-123",
        )

        assert result.order_number == "ORD-123"

    def test_build_conversation_response_includes_has_order(self) -> None:
        conversation = _make_builder_conversation("voice", ["voice:+15551112222"])

        result = _builder.build_conversation(
            conversation=conversation,
            message_count=1,
            last_message=None,
            has_order=True,
        )

        assert result.has_order is True
        assert result.order_number is None

    def test_build_conversation_detail_response_includes_order_number(self) -> None:
        conversation = _make_builder_conversation("voice", ["voice:+15551112222"])

        result = _builder.build_conversation_detail(
            conversation,
            order_number="ORD-456",
        )

        assert result.order_number == "ORD-456"

    def test_build_conversation_detail_response_includes_has_order(self) -> None:
        conversation = _make_builder_conversation("voice", ["voice:+15551112222"])

        result = _builder.build_conversation_detail(
            conversation,
            has_order=True,
        )

        assert result.has_order is True
        assert result.order_number is None


class TestListAccountConversationsOrderNumber:
    """Verify admin conversation list responses include order numbers."""

    @pytest.mark.asyncio
    async def test_passes_preview_order_number_to_response(self) -> None:
        account = MagicMock()
        account.id = uuid.uuid4()
        conversation = _make_builder_conversation("voice", ["voice:+15551112222"])
        preview = SimpleNamespace(
            conversation=conversation,
            last_message=None,
            message_count=1,
            order_number="ORD-123",
            has_order=True,
        )

        with (
            patch("api.routes.admin._conversation.account_service") as mock_account,
            patch("api.routes.admin._conversation.admin_service") as mock_admin,
        ):
            mock_account.get_account.return_value = account
            mock_admin.list_conversations_in_account.return_value = (1, [preview])
            mock_admin.get_conversation_filter_values.return_value = ([], [], [])

            result = await list_account_conversations(
                account_name="test-account",
                keyword="",
                channel=None,
                project_id=None,
                lookback=None,
                page=1,
                page_size=10,
                escalated=False,
                hide_testing_sessions=True,
                language=None,
                purpose=None,
                ended_reason=None,
                customer_converted=None,
                context=_make_context(),
                session=MagicMock(),
            )

        assert result.sessions[0].order_number == "ORD-123"
        assert result.sessions[0].has_order is True

    @pytest.mark.asyncio
    async def test_get_detail_includes_order_info(self) -> None:
        conversation = _make_builder_conversation(
            "voice",
            ["voice:+15551112222"],
        )
        conversation.user.account.name = "test-account"

        with patch("api.routes.admin._conversation.admin_service") as mock_admin:
            mock_admin.get_conversation_by_id.return_value = conversation
            mock_admin.get_conversation_order_display_info.return_value = (
                SimpleNamespace(order_number="ORD-456", has_order=True)
            )

            result = await get_conversation_detail(
                account_name="test-account",
                conversation_id=conversation.id,
                context=_make_context(),
                session=MagicMock(),
            )

        assert result.order_number == "ORD-456"
        assert result.has_order is True


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
