"""Tests for feedback creation with author name lookup."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.routes.admin._feedback import create_feedback
from api.schemas.admin.feedback import CreateFeedbackRequest, FeedbackReaction
from db.tables.account_user import AccountUser


class TestCreateFeedback:
    """Tests for create_feedback function with author_name population."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock user context."""
        from services.auth_types import UserRole

        context = MagicMock()
        context.email = "test@example.com"
        context.username = str(uuid.uuid4())
        context.display_name = ""  # Empty display_name to test DB lookup
        context.role = UserRole.Admin  # Admin to bypass permission check
        return context

    @pytest.fixture
    def mock_feedback_request(self):
        """Create a mock feedback creation request."""
        return CreateFeedbackRequest(
            message_id=uuid.uuid4(),
            reaction=FeedbackReaction.THUMBS_DOWN,
            note="Test feedback",
            tags=None,
        )

    @pytest.fixture
    def mock_message(self):
        """Create a mock message with conversation and account."""
        message = MagicMock()
        message.id = uuid.uuid4()
        message.conversation = MagicMock()
        message.conversation.id = uuid.uuid4()
        message.conversation.user = MagicMock()
        message.conversation.user.account = MagicMock()
        message.conversation.user.account.id = uuid.uuid4()
        message.conversation.user.account.name = "test-account"
        return message

    @pytest.fixture
    def mock_services(self, mock_message):
        """Set up common service mocks for feedback creation tests."""
        with (
            patch("api.routes.admin._feedback.message_service") as mock_message_service,
            patch(
                "api.routes.admin._feedback.AccountUserRepository"
            ) as mock_account_user_repo,
            patch(
                "api.routes.admin._feedback.feedback_service"
            ) as mock_feedback_service,
            patch("api.routes.admin._feedback._builder") as mock_builder,
            patch("api.routes.admin._feedback.notion_service") as mock_notion,
            patch("api.routes.admin._feedback.slack_service") as mock_slack,
        ):
            # Setup default mocks
            mock_message_service.get_message_by_id.return_value = mock_message
            mock_builder.build_feedback.return_value = MagicMock()

            # Use AsyncMock for async service methods
            mock_notion.create_feedback_ticket = AsyncMock(return_value=None)
            mock_notion.extract_notion_page_id = AsyncMock(return_value=None)
            mock_slack.send_feedback_notification = AsyncMock(return_value=None)

            # Return mock instances for per-test customization
            yield {
                "message_service": mock_message_service,
                "account_user_repo": mock_account_user_repo,
                "feedback_service": mock_feedback_service,
                "builder": mock_builder,
                "notion": mock_notion,
                "slack": mock_slack,
            }

    @pytest.mark.asyncio
    async def test_author_name_from_account_user_table(
        self, mock_context, mock_feedback_request, mock_services
    ):
        """Should use name from account_users table when available."""
        mock_session = MagicMock()

        # Create a mock AccountUser with name
        mock_account_user = MagicMock(spec=AccountUser)
        mock_account_user.name = "John Doe"
        mock_account_user.email = "test@example.com"

        # Setup AccountUserRepository mock
        mock_repo_instance = mock_services["account_user_repo"].return_value
        mock_repo_instance.get_by_user_and_account.return_value = mock_account_user

        # Mock persisted feedback
        mock_persisted_feedback = MagicMock()
        mock_persisted_feedback.id = uuid.uuid4()
        mock_persisted_feedback.reaction = "thumbs_down"
        mock_persisted_feedback.author_name = "John Doe"
        mock_persisted_feedback.note = "Test feedback"
        mock_persisted_feedback.tags = None
        mock_services["feedback_service"].create_feedback.return_value = (
            mock_persisted_feedback
        )

        # Execute
        await create_feedback(mock_feedback_request, mock_context, mock_session)

        # Assert AccountUserRepository was called with correct account
        mock_services["account_user_repo"].assert_called_once_with(
            mock_session, auto_commit=False
        )
        mock_repo_instance.get_by_user_and_account.assert_called_once()

        # Assert feedback was created with correct author_name
        create_call = mock_services["feedback_service"].create_feedback.call_args
        created_feedback = create_call[0][1]
        assert created_feedback.author_name == "John Doe"
        assert created_feedback.author_identifier == "test@example.com"

    @pytest.mark.asyncio
    async def test_author_name_fallback_to_display_name(
        self, mock_feedback_request, mock_services
    ):
        """Should fall back to display_name when account_users record not found."""
        from services.auth_types import UserRole

        mock_session = MagicMock()

        # Create context with display_name
        mock_context = MagicMock()
        mock_context.email = "test@example.com"
        mock_context.username = str(uuid.uuid4())
        mock_context.display_name = "Display Name"
        mock_context.role = UserRole.Admin

        # Mock AccountUserRepository returning None
        mock_repo_instance = mock_services["account_user_repo"].return_value
        mock_repo_instance.get_by_user_and_account.return_value = None

        # Mock persisted feedback
        mock_persisted_feedback = MagicMock()
        mock_persisted_feedback.id = uuid.uuid4()
        mock_persisted_feedback.reaction = "thumbs_down"
        mock_persisted_feedback.author_name = "Display Name"
        mock_persisted_feedback.note = "Test feedback"
        mock_persisted_feedback.tags = None
        mock_services["feedback_service"].create_feedback.return_value = (
            mock_persisted_feedback
        )

        # Execute
        await create_feedback(mock_feedback_request, mock_context, mock_session)

        # Assert feedback was created with display_name
        create_call = mock_services["feedback_service"].create_feedback.call_args
        created_feedback = create_call[0][1]
        assert created_feedback.author_name == "Display Name"

    @pytest.mark.asyncio
    async def test_author_name_fallback_to_email(
        self, mock_feedback_request, mock_services
    ):
        """Should fall back to email when both account_user and display_name are empty."""
        from services.auth_types import UserRole

        mock_session = MagicMock()

        # Create context with empty display_name
        mock_context = MagicMock()
        mock_context.email = "test@example.com"
        mock_context.username = str(uuid.uuid4())
        mock_context.display_name = ""
        mock_context.role = UserRole.Admin

        # Mock AccountUserRepository returning None
        mock_repo_instance = mock_services["account_user_repo"].return_value
        mock_repo_instance.get_by_user_and_account.return_value = None

        # Mock persisted feedback
        mock_persisted_feedback = MagicMock()
        mock_persisted_feedback.id = uuid.uuid4()
        mock_persisted_feedback.reaction = "thumbs_down"
        mock_persisted_feedback.author_name = "test@example.com"
        mock_persisted_feedback.note = "Test feedback"
        mock_persisted_feedback.tags = None
        mock_services["feedback_service"].create_feedback.return_value = (
            mock_persisted_feedback
        )

        # Execute
        await create_feedback(mock_feedback_request, mock_context, mock_session)

        # Assert feedback was created with email
        create_call = mock_services["feedback_service"].create_feedback.call_args
        created_feedback = create_call[0][1]
        assert created_feedback.author_name == "test@example.com"

    @pytest.mark.asyncio
    async def test_author_name_when_account_user_name_is_empty(
        self, mock_context, mock_feedback_request, mock_services
    ):
        """Should fall back to display_name when account_user.name is empty string."""
        mock_session = MagicMock()

        # Update context to have display_name
        mock_context.display_name = "JWT Display Name"

        # Create a mock AccountUser with empty name
        mock_account_user = MagicMock(spec=AccountUser)
        mock_account_user.name = ""  # Empty name
        mock_account_user.email = "test@example.com"

        # Mock AccountUserRepository
        mock_repo_instance = mock_services["account_user_repo"].return_value
        mock_repo_instance.get_by_user_and_account.return_value = mock_account_user

        # Mock persisted feedback
        mock_persisted_feedback = MagicMock()
        mock_persisted_feedback.id = uuid.uuid4()
        mock_persisted_feedback.reaction = "thumbs_down"
        mock_persisted_feedback.author_name = "JWT Display Name"
        mock_persisted_feedback.note = "Test feedback"
        mock_persisted_feedback.tags = None
        mock_services["feedback_service"].create_feedback.return_value = (
            mock_persisted_feedback
        )

        # Execute
        await create_feedback(mock_feedback_request, mock_context, mock_session)

        # Assert feedback was created with JWT display_name
        create_call = mock_services["feedback_service"].create_feedback.call_args
        created_feedback = create_call[0][1]
        assert created_feedback.author_name == "JWT Display Name"
