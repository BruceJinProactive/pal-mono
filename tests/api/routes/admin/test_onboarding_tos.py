"""Tests for TOS acceptance during self-onboarding."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response

from api.routes.admin._onboarding import self_onboarding
from api.schemas.admin.account import AccountStatusResponse
from api.schemas.admin.onboarding import SelfOnboardingRequest
from db.tables.accounts import AccountSegment, AccountStatus

# Test fixture constant for password
TEST_PASSWORD = "TestPassword123!"  # noqa: S106


class TestSelfOnboardingTOSIntegration:
    """Integration tests for TOS acceptance in self_onboarding function."""

    @pytest.mark.asyncio
    async def test_self_onboarding_with_terms_accepted(self):
        """Test self_onboarding creates TOS acceptance when terms_accepted=True."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="test@example.com",
            user_name="Test User",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=True,  # Test with TOS accepted
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.id = uuid.uuid4()
        mock_account.name = "test-account"
        mock_account.display_name = "Test Account"

        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.session = MagicMock()
        mock_user.session.user_sub = str(uuid.uuid4())

        mock_account_status = AccountStatusResponse(
            id=mock_account.id,
            name="test-account",
            status=AccountStatus.active,
            display_name="Test Account",
        )

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch("api.routes.admin._onboarding.account_service") as mock_account_svc,
            patch(
                "api.routes.admin._onboarding.TosAcceptanceRepository"
            ) as mock_tos_repo,
            patch(
                "api.routes.admin._onboarding.slack_service.send_self_onboarding_notification",
                new_callable=AsyncMock,
            ),
            patch("api.routes.admin._onboarding._set_user_session"),
            patch(
                "api.routes.admin._onboarding.get_account_status",
                return_value=mock_account_status,
            ),
        ):
            mock_account_svc.get_account.return_value = mock_account
            mock_account_svc.CURRENT_TOS_VERSION = "v1.0"

            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = (
                None  # No existing acceptance
            )
            tos_repo_instance.create_tos_acceptance.return_value = MagicMock()

            result = await self_onboarding(request, mock_response, mock_session)

            # Verify function returned successfully
            assert result is not None
            assert result.success is True

            # Verify TOS acceptance was created
            tos_repo_instance.create_tos_acceptance.assert_called_once()
            call_kwargs = tos_repo_instance.create_tos_acceptance.call_args[1]
            assert call_kwargs["account_id"] == mock_account.id
            assert call_kwargs["display_name"] == mock_account.display_name
            assert call_kwargs["tos_version"] == "v1.0"
            assert call_kwargs["user_id"] == uuid.UUID(mock_user.session.user_sub)
            assert call_kwargs["user_email"] == "test@example.com"
            assert isinstance(call_kwargs["accepted_at"], datetime)

            # Verify session was committed
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_self_onboarding_with_existing_tos_acceptance(self):
        """Test self_onboarding is idempotent when TOS acceptance already exists."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="test@example.com",
            user_name="Test User",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=True,  # Test with TOS accepted
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.id = uuid.uuid4()
        mock_account.name = "test-account"
        mock_account.display_name = "Test Account"

        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.session = MagicMock()
        mock_user.session.user_sub = str(uuid.uuid4())

        mock_account_status = AccountStatusResponse(
            id=mock_account.id,
            name="test-account",
            status=AccountStatus.active,
            display_name="Test Account",
        )

        # Existing TOS acceptance record
        existing_tos = MagicMock()
        existing_tos.account_id = mock_account.id
        existing_tos.tos_version = "v1.0"

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch("api.routes.admin._onboarding.account_service") as mock_account_svc,
            patch(
                "api.routes.admin._onboarding.TosAcceptanceRepository"
            ) as mock_tos_repo,
            patch(
                "api.routes.admin._onboarding.slack_service.send_self_onboarding_notification",
                new_callable=AsyncMock,
            ),
            patch("api.routes.admin._onboarding._set_user_session"),
            patch(
                "api.routes.admin._onboarding.get_account_status",
                return_value=mock_account_status,
            ),
        ):
            mock_account_svc.get_account.return_value = mock_account
            mock_account_svc.CURRENT_TOS_VERSION = "v1.0"

            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = (
                existing_tos  # Existing acceptance found
            )

            result = await self_onboarding(request, mock_response, mock_session)

            # Verify function returned successfully
            assert result is not None
            assert result.success is True

            # Verify TOS acceptance was NOT created (already exists)
            tos_repo_instance.create_tos_acceptance.assert_not_called()

            # Verify get_tos_acceptance_by_version was called to check for existing acceptance
            tos_repo_instance.get_tos_acceptance_by_version.assert_called_once_with(
                account_id=mock_account.id,
                tos_version="v1.0",
            )

            # Verify session was committed
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_self_onboarding_without_terms_accepted(self):
        """Test self_onboarding skips TOS creation when terms_accepted=False."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="test@example.com",
            user_name="Test User",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=False,  # Test without TOS accepted
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.session = MagicMock()

        mock_account_status = AccountStatusResponse(
            id=uuid.uuid4(),
            name="test-account",
            status=AccountStatus.active,
            display_name="Test Account",
        )

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch(
                "api.routes.admin._onboarding.TosAcceptanceRepository"
            ) as mock_tos_repo,
            patch(
                "api.routes.admin._onboarding.slack_service.send_self_onboarding_notification",
                new_callable=AsyncMock,
            ),
            patch("api.routes.admin._onboarding._set_user_session"),
            patch(
                "api.routes.admin._onboarding.get_account_status",
                return_value=mock_account_status,
            ),
        ):
            tos_repo_instance = mock_tos_repo.return_value

            result = await self_onboarding(request, mock_response, mock_session)

            # Verify function returned successfully
            assert result is not None
            assert result.success is True

            # Verify TOS acceptance was NOT created
            tos_repo_instance.create_tos_acceptance.assert_not_called()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_self_onboarding_tos_account_not_found(self):
        """Test self_onboarding raises error when account cannot be retrieved for TOS."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="test@example.com",
            user_name="Test User",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=True,
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.session = MagicMock()
        mock_user.session.user_sub = str(uuid.uuid4())

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch("api.routes.admin._onboarding.account_service") as mock_account_svc,
        ):
            # Account retrieval returns None
            mock_account_svc.get_account.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await self_onboarding(request, mock_response, mock_session)

            assert exc_info.value.status_code == 500
            assert (
                "Account was created but cannot be retrieved" in exc_info.value.detail
            )

    @pytest.mark.asyncio
    async def test_self_onboarding_tos_creation_failure(self):
        """Test self_onboarding handles TOS creation failure and rolls back."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="test@example.com",
            user_name="Test User",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=True,
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.id = uuid.uuid4()
        mock_account.name = "test-account"
        mock_account.display_name = "Test Account"

        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.session = MagicMock()
        mock_user.session.user_sub = str(uuid.uuid4())

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch("api.routes.admin._onboarding.account_service") as mock_account_svc,
            patch(
                "api.routes.admin._onboarding.TosAcceptanceRepository"
            ) as mock_tos_repo,
            patch("api.routes.admin._onboarding.logger"),
        ):
            mock_account_svc.get_account.return_value = mock_account
            mock_account_svc.CURRENT_TOS_VERSION = "v1.0"

            # Make TOS creation fail
            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = (
                None  # No existing acceptance
            )
            tos_repo_instance.create_tos_acceptance.side_effect = Exception(
                "Database error"
            )

            with pytest.raises(HTTPException) as exc_info:
                await self_onboarding(request, mock_response, mock_session)

            # Verify error handling
            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Failed to record TOS acceptance"
            mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_self_onboarding_tos_metrics_failure_on_duplicate(self):
        """Test self_onboarding continues successfully when acceptance exists (OTel never throws)."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="test@example.com",
            user_name="Test User",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=True,
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.id = uuid.uuid4()
        mock_account.name = "test-account"
        mock_account.display_name = "Test Account"

        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.session = MagicMock()
        mock_user.session.user_sub = str(uuid.uuid4())

        mock_account_status = AccountStatusResponse(
            id=mock_account.id,
            name="test-account",
            status=AccountStatus.active,
            display_name="Test Account",
        )

        # Existing TOS acceptance record
        existing_tos = MagicMock()
        existing_tos.account_id = mock_account.id
        existing_tos.tos_version = "v1.0"

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch("api.routes.admin._onboarding.account_service") as mock_account_svc,
            patch(
                "api.routes.admin._onboarding.TosAcceptanceRepository"
            ) as mock_tos_repo,
            patch(
                "api.routes.admin._onboarding.slack_service.send_self_onboarding_notification",
                new_callable=AsyncMock,
            ),
            patch("api.routes.admin._onboarding._set_user_session"),
            patch(
                "api.routes.admin._onboarding.get_account_status",
                return_value=mock_account_status,
            ),
            patch("api.routes.admin._onboarding.increment_counter") as mock_increment,
        ):
            mock_account_svc.get_account.return_value = mock_account
            mock_account_svc.CURRENT_TOS_VERSION = "v1.0"

            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = (
                existing_tos  # Existing acceptance found
            )

            result = await self_onboarding(request, mock_response, mock_session)

            # Verify function still succeeds
            assert result is not None
            assert result.success is True

            # Verify exact OTel metric payload was emitted
            mock_increment.assert_any_call(
                "tos.acceptance.duplicate",
                attributes={
                    "version": "v1.0",
                    "source": "onboarding",
                },
            )

            # Verify session was still committed
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_self_onboarding_tos_metrics_failure_on_create(self):
        """Test self_onboarding continues successfully when creating acceptance (OTel never throws)."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="test@example.com",
            user_name="Test User",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=True,
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.id = uuid.uuid4()
        mock_account.name = "test-account"
        mock_account.display_name = "Test Account"

        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.session = MagicMock()
        mock_user.session.user_sub = str(uuid.uuid4())

        mock_account_status = AccountStatusResponse(
            id=mock_account.id,
            name="test-account",
            status=AccountStatus.active,
            display_name="Test Account",
        )

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch("api.routes.admin._onboarding.account_service") as mock_account_svc,
            patch(
                "api.routes.admin._onboarding.TosAcceptanceRepository"
            ) as mock_tos_repo,
            patch(
                "api.routes.admin._onboarding.slack_service.send_self_onboarding_notification",
                new_callable=AsyncMock,
            ),
            patch("api.routes.admin._onboarding._set_user_session"),
            patch(
                "api.routes.admin._onboarding.get_account_status",
                return_value=mock_account_status,
            ),
            patch("api.routes.admin._onboarding.increment_counter") as mock_increment,
        ):
            mock_account_svc.get_account.return_value = mock_account
            mock_account_svc.CURRENT_TOS_VERSION = "v1.0"

            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = (
                None  # No existing acceptance
            )
            tos_repo_instance.create_tos_acceptance.return_value = MagicMock()

            result = await self_onboarding(request, mock_response, mock_session)

            # Verify function still succeeds
            assert result is not None
            assert result.success is True

            # Verify exact OTel metric payload was emitted
            mock_increment.assert_any_call(
                "tos.acceptance.created",
                attributes={
                    "version": "v1.0",
                    "source": "onboarding",
                },
            )

            # Verify TOS was still created
            tos_repo_instance.create_tos_acceptance.assert_called_once()

            # Verify session was still committed
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_self_onboarding_tos_metrics_failure_on_error(self):
        """Test self_onboarding emits error metric during TOS creation error (OTel never throws)."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="test@example.com",
            user_name="Test User",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=True,
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.id = uuid.uuid4()
        mock_account.name = "test-account"
        mock_account.display_name = "Test Account"

        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.session = MagicMock()
        mock_user.session.user_sub = str(uuid.uuid4())

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch("api.routes.admin._onboarding.account_service") as mock_account_svc,
            patch(
                "api.routes.admin._onboarding.TosAcceptanceRepository"
            ) as mock_tos_repo,
            patch("api.routes.admin._onboarding.increment_counter") as mock_increment,
        ):
            mock_account_svc.get_account.return_value = mock_account
            mock_account_svc.CURRENT_TOS_VERSION = "v1.0"

            # Make TOS creation fail
            tos_repo_instance = mock_tos_repo.return_value
            tos_repo_instance.get_tos_acceptance_by_version.return_value = (
                None  # No existing acceptance
            )
            tos_repo_instance.create_tos_acceptance.side_effect = Exception(
                "Database error"
            )

            with pytest.raises(HTTPException) as exc_info:
                await self_onboarding(request, mock_response, mock_session)

            # Verify error handling still works
            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Failed to record TOS acceptance"
            mock_session.rollback.assert_called_once()

            # Verify exact OTel metric payload was emitted
            mock_increment.assert_any_call(
                "tos.acceptance.failed",
                attributes={
                    "version": "v1.0",
                    "error": "Exception",
                    "source": "onboarding",
                },
            )

    @pytest.mark.asyncio
    async def test_self_onboarding_internal_email_skips_tos_proactiveailab(self):
        """Test self_onboarding skips TOS creation for @proactiveailab.com emails."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="internal@proactiveailab.com",  # Internal email
            user_name="Internal User",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=True,  # TOS acceptance requested
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.email = "internal@proactiveailab.com"
        mock_user.session = MagicMock()
        mock_user.session.user_sub = str(uuid.uuid4())

        mock_account_status = AccountStatusResponse(
            id=uuid.uuid4(),
            name="test-account",
            status=AccountStatus.active,
            display_name="Test Account",
        )

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch("api.routes.admin._onboarding.account_service"),
            patch(
                "api.routes.admin._onboarding.TosAcceptanceRepository"
            ) as mock_tos_repo,
            patch(
                "api.routes.admin._onboarding.slack_service.send_self_onboarding_notification",
                new_callable=AsyncMock,
            ),
            patch("api.routes.admin._onboarding._set_user_session"),
            patch(
                "api.routes.admin._onboarding.get_account_status",
                return_value=mock_account_status,
            ),
            patch("api.routes.admin._onboarding.logger") as mock_logger,
        ):
            tos_repo_instance = mock_tos_repo.return_value

            # Execute
            result = await self_onboarding(request, mock_response, mock_session)

            # Verify signup succeeded
            assert result is not None
            mock_session.commit.assert_called_once()

            # Verify TOS acceptance was NOT created (skipped for internal email)
            tos_repo_instance.create_tos_acceptance.assert_not_called()
            tos_repo_instance.get_tos_acceptance_by_version.assert_not_called()

            # Verify internal email skip was logged
            mock_logger.info.assert_any_call(
                "Skipping TOS acceptance for internal email: internal@proactiveailab.com"
            )

    @pytest.mark.asyncio
    async def test_self_onboarding_internal_email_skips_tos_palona(self):
        """Test self_onboarding skips TOS creation for @palona.ai emails."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="team@palona.ai",  # Internal email
            user_name="Team Member",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=True,  # TOS acceptance requested
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.email = "team@palona.ai"
        mock_user.session = MagicMock()
        mock_user.session.user_sub = str(uuid.uuid4())

        mock_account_status = AccountStatusResponse(
            id=uuid.uuid4(),
            name="test-account",
            status=AccountStatus.active,
            display_name="Test Account",
        )

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch("api.routes.admin._onboarding.account_service"),
            patch(
                "api.routes.admin._onboarding.TosAcceptanceRepository"
            ) as mock_tos_repo,
            patch(
                "api.routes.admin._onboarding.slack_service.send_self_onboarding_notification",
                new_callable=AsyncMock,
            ),
            patch("api.routes.admin._onboarding._set_user_session"),
            patch(
                "api.routes.admin._onboarding.get_account_status",
                return_value=mock_account_status,
            ),
            patch("api.routes.admin._onboarding.logger") as mock_logger,
        ):
            tos_repo_instance = mock_tos_repo.return_value

            # Execute
            result = await self_onboarding(request, mock_response, mock_session)

            # Verify signup succeeded
            assert result is not None
            mock_session.commit.assert_called_once()

            # Verify TOS acceptance was NOT created (skipped for internal email)
            tos_repo_instance.create_tos_acceptance.assert_not_called()
            tos_repo_instance.get_tos_acceptance_by_version.assert_not_called()

            # Verify internal email skip was logged
            mock_logger.info.assert_any_call(
                "Skipping TOS acceptance for internal email: team@palona.ai"
            )

    @pytest.mark.asyncio
    async def test_self_onboarding_internal_email_case_insensitive(self):
        """Test internal email check is case-insensitive."""
        request = SelfOnboardingRequest(
            account_name="test-account",
            account_display_name="Test Account",
            account_description="Test business",
            email="USER@PALONA.AI",  # Uppercase internal email
            user_name="User",
            password=TEST_PASSWORD,
            phone_number="+15555555555",
            agent_name="Test Agent",
            agent_greeting_message="Hello",
            agent_communication_style="friendly",
            agent_interaction_guidelines="Be helpful",
            agent_voice_id="voice123",
            agent_language="English",
            project_name="test-project",
            project_display_name="Test Project",
            project_store_hours="Mon-Fri: 9am-5pm",
            project_address="123 Test St",
            project_timezone="America/Los_Angeles",
            terms_accepted=True,
            segment=AccountSegment.smb,
        )

        mock_response = MagicMock(spec=Response)
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.email = "USER@PALONA.AI"
        mock_user.session = MagicMock()
        mock_user.session.user_sub = str(uuid.uuid4())

        mock_account_status = AccountStatusResponse(
            id=uuid.uuid4(),
            name="test-account",
            status=AccountStatus.active,
            display_name="Test Account",
        )

        with (
            patch(
                "api.routes.admin._onboarding.self_onboard_account",
                return_value="test-account",
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_agent",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_project",
                return_value=uuid.uuid4(),
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_voice_config",
                new_callable=AsyncMock,
            ),
            patch(
                "api.routes.admin._onboarding.self_onboard_user", return_value=mock_user
            ),
            patch("api.routes.admin._onboarding.account_service"),
            patch(
                "api.routes.admin._onboarding.TosAcceptanceRepository"
            ) as mock_tos_repo,
            patch(
                "api.routes.admin._onboarding.slack_service.send_self_onboarding_notification",
                new_callable=AsyncMock,
            ),
            patch("api.routes.admin._onboarding._set_user_session"),
            patch(
                "api.routes.admin._onboarding.get_account_status",
                return_value=mock_account_status,
            ),
            patch("api.routes.admin._onboarding.logger") as mock_logger,
        ):
            tos_repo_instance = mock_tos_repo.return_value

            # Execute
            result = await self_onboarding(request, mock_response, mock_session)

            # Verify signup succeeded
            assert result is not None

            # Verify TOS acceptance was NOT created (case-insensitive check should work)
            tos_repo_instance.create_tos_acceptance.assert_not_called()

            # Verify internal email skip was logged
            mock_logger.info.assert_any_call(
                "Skipping TOS acceptance for internal email: USER@PALONA.AI"
            )
