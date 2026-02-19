# pyright: reportAttributeAccessIssue=false
"""Business-driven tests for NumberService LiveKit provisioning.

These tests verify the dual-stack provisioning behavior:
- Vapi path (default): purchase → import to Vapi
- LiveKit path: purchase → SIP trunk → dispatch rule (no local DB)
- Release paths for both providers using LiveKit API lookups
- Backward compatibility (no voice_provider param defaults to Vapi)
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from services.number_service._livekit_sip import LiveKitProvisionResult


class TestSetupNumberVapiPath:
    """Verify that Vapi provisioning (default path) is unchanged."""

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_setup_number_defaults_to_vapi(self, mock_twilio_cls, mock_vapi_cls, _):
        """Calling setup_number without voice_provider imports to Vapi."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
            },
        ):
            service = NumberService()

        # Set string values for Twilio credentials (Vapi SDK validates types)
        service.twilio_client.username = "ACtest"
        service.twilio_client.password = "token"

        # Mock Twilio purchase
        mock_twilio_number = MagicMock()
        mock_twilio_number.phone_number = "+15551234567"
        mock_twilio_number.sid = "PN123"
        service.twilio_client.available_phone_numbers.return_value.toll_free.list.return_value = [
            mock_twilio_number
        ]
        service.twilio_client.incoming_phone_numbers.create.return_value = (
            mock_twilio_number
        )

        result = service.setup_number(
            country_code="US",
            toll_free=True,
            merchant_name="Test Business",
            purchase_number=True,
        )

        assert result.number == "+15551234567"
        # Vapi import should have been called
        service.vapi_client.phone_numbers.create.assert_called_once()

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_setup_number_explicit_vapi_imports_to_vapi(
        self, mock_twilio_cls, mock_vapi_cls, _
    ):
        """Explicitly passing voice_provider='vapi' imports to Vapi."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
            },
        ):
            service = NumberService()

        # Set string values for Twilio credentials (Vapi SDK validates types)
        service.twilio_client.username = "ACtest"
        service.twilio_client.password = "token"

        mock_twilio_number = MagicMock()
        mock_twilio_number.phone_number = "+15559999999"
        mock_twilio_number.sid = "PN999"
        service.twilio_client.available_phone_numbers.return_value.toll_free.list.return_value = [
            mock_twilio_number
        ]
        service.twilio_client.incoming_phone_numbers.create.return_value = (
            mock_twilio_number
        )

        result = service.setup_number(
            country_code="US",
            toll_free=True,
            merchant_name="Test",
            purchase_number=True,
            voice_provider="vapi",
        )

        assert result.number == "+15559999999"
        service.vapi_client.phone_numbers.create.assert_called_once()


class TestSetupNumberLiveKitPath:
    """Verify that LiveKit provisioning creates dispatch rules instead of Vapi import."""

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_setup_number_livekit_creates_dispatch_rule(
        self, mock_twilio_cls, mock_vapi_cls, mock_lk_cls
    ):
        """LiveKit path: purchases number, sets SIP trunk, creates dispatch rule."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
                "TWILIO_SIP_TRUNK_SID": "TK-sip-trunk",
            },
        ):
            service = NumberService()

        # Mock LiveKit client as configured
        service._livekit_client.is_configured.return_value = True
        service._livekit_client.create_dispatch_rule.return_value = (
            LiveKitProvisionResult(trunk_id="trunk-abc", dispatch_rule_id="DR-123")
        )

        # Mock Twilio purchase
        mock_twilio_number = MagicMock()
        mock_twilio_number.phone_number = "+15551234567"
        mock_twilio_number.sid = "PN123"
        service.twilio_client.available_phone_numbers.return_value.toll_free.list.return_value = [
            mock_twilio_number
        ]
        service.twilio_client.incoming_phone_numbers.create.return_value = (
            mock_twilio_number
        )

        # Mock Twilio number details (for trunk update)
        mock_number_details = MagicMock()
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]
        mock_number_details.phone_number = "+15551234567"

        result = service.setup_number(
            country_code="US",
            toll_free=True,
            merchant_name="Test Business",
            purchase_number=True,
            voice_provider="livekit",
        )

        assert result.number == "+15551234567"
        # Vapi should NOT have been called
        service.vapi_client.phone_numbers.create.assert_not_called()
        # LiveKit dispatch rule should have been created
        service._livekit_client.create_dispatch_rule.assert_called_once_with(
            "+15551234567"
        )

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_setup_number_livekit_not_configured_raises(
        self, mock_twilio_cls, mock_vapi_cls, _
    ):
        """LiveKit path when LiveKit is not configured raises ValueError."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
                "TWILIO_SIP_TRUNK_SID": "TK-trunk",
            },
        ):
            service = NumberService()

        service._livekit_client.is_configured.return_value = False

        mock_twilio_number = MagicMock()
        mock_twilio_number.phone_number = "+15551234567"
        mock_twilio_number.sid = "PN123"
        service.twilio_client.available_phone_numbers.return_value.toll_free.list.return_value = [
            mock_twilio_number
        ]
        service.twilio_client.incoming_phone_numbers.create.return_value = (
            mock_twilio_number
        )

        with pytest.raises(ValueError, match="LiveKit is not configured"):
            service.setup_number(
                country_code="US",
                toll_free=True,
                merchant_name="Test",
                purchase_number=True,
                voice_provider="livekit",
            )


class TestSetupNumberLiveKitRollback:
    """Verify that LiveKit provisioning rollback works on failure."""

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_livekit_dispatch_rule_failure_rolls_back_trunk(
        self, mock_twilio_cls, mock_vapi_cls, mock_lk_cls
    ):
        """If dispatch rule creation fails, Twilio trunk config is reverted."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
                "TWILIO_SIP_TRUNK_SID": "TK-sip-trunk",
            },
        ):
            service = NumberService()

        service._livekit_client.is_configured.return_value = True
        service._livekit_client.create_dispatch_rule.side_effect = ValueError(
            "API error"
        )

        mock_number_details = MagicMock()
        mock_number_details.phone_number = "+15551234567"
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        mock_twilio_number = MagicMock()
        mock_twilio_number.phone_number = "+15551234567"
        mock_twilio_number.sid = "PN123"
        service.twilio_client.available_phone_numbers.return_value.toll_free.list.return_value = [
            mock_twilio_number
        ]
        service.twilio_client.incoming_phone_numbers.create.return_value = (
            mock_twilio_number
        )

        with pytest.raises(ValueError, match="Failed to provision number for LiveKit"):
            service.setup_number(
                country_code="US",
                toll_free=True,
                merchant_name="Test",
                purchase_number=True,
                voice_provider="livekit",
            )

        # Twilio trunk should have been reverted
        mock_number_details.update.assert_any_call(trunk_sid="")


class TestDeleteNumberDualStack:
    """Verify delete_number routes to correct provider via LiveKit API lookup."""

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_delete_livekit_number_cleans_up_dispatch_rule(
        self, mock_twilio_cls, mock_vapi_cls, mock_lk_cls
    ):
        """Deleting a LiveKit number finds and removes dispatch rule via API."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
            },
        ):
            service = NumberService()

        # Mock: LiveKit API says this number has a dispatch rule
        service._livekit_client.has_dispatch_rule.return_value = True
        service._livekit_client.find_dispatch_rule_by_number.return_value = (
            "DR-to-delete"
        )

        # Mock: Twilio number details for trunk revert
        mock_number_details = MagicMock()
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        service.delete_number("+15551234567")

        # Dispatch rule should have been deleted via API lookup
        service._livekit_client.delete_dispatch_rule_by_number.assert_called_once_with(
            "+15551234567"
        )
        # Twilio number should have been deleted
        service.twilio_client.incoming_phone_numbers.list.assert_called()

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_delete_vapi_number_releases_from_vapi(
        self, mock_twilio_cls, mock_vapi_cls, mock_lk_cls
    ):
        """Deleting a Vapi number (no LiveKit dispatch rule) uses Vapi path."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
            },
        ):
            service = NumberService()

        # Mock: LiveKit API says no dispatch rule for this number
        service._livekit_client.has_dispatch_rule.return_value = False

        # Mock Vapi phone numbers list
        mock_vapi_number = MagicMock()
        mock_vapi_number.number = "+15551234567"
        mock_vapi_number.id = "vapi-id-123"
        service.vapi_client.phone_numbers.list.return_value = [mock_vapi_number]

        # Mock Twilio
        service.twilio_client.incoming_phone_numbers.list.return_value = []

        service.delete_number("+15551234567")

        # Vapi should have been called to delete
        service.vapi_client.phone_numbers.delete.assert_called_once_with(
            id="vapi-id-123"
        )
        # LiveKit release should NOT have been called
        service._livekit_client.delete_dispatch_rule_by_number.assert_not_called()


class TestReleaseNumberWithOptionsDualStack:
    """Verify release_number_with_options handles both providers via API lookup."""

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_return_to_pool_livekit_cleans_up_and_sets_available(
        self, mock_twilio_cls, mock_vapi_cls, mock_lk_cls
    ):
        """Returning a LiveKit number to pool cleans up dispatch rule AND sets available."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
            },
        ):
            service = NumberService()

        # Mock: LiveKit API says this number has a dispatch rule
        service._livekit_client.has_dispatch_rule.return_value = True
        service._livekit_client.find_dispatch_rule_by_number.return_value = "DR-pool"

        mock_number_details = MagicMock()
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        service.release_number_with_options("+15551234567", "return_to_pool")

        # Dispatch rule cleaned up via API
        service._livekit_client.delete_dispatch_rule_by_number.assert_called_once_with(
            "+15551234567"
        )
        # Friendly name set to AVAILABLE
        mock_number_details.update.assert_called()

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_return_to_pool_vapi_sets_available(
        self, mock_twilio_cls, mock_vapi_cls, _
    ):
        """Returning a Vapi number to pool just sets available."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
            },
        ):
            service = NumberService()

        # Mock: LiveKit API says no dispatch rule
        service._livekit_client.has_dispatch_rule.return_value = False

        mock_number_details = MagicMock()
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        service.release_number_with_options("+15551234567", "return_to_pool")

        mock_number_details.update.assert_called()
        # LiveKit should not be involved
        service._livekit_client.delete_dispatch_rule_by_number.assert_not_called()


class TestReserveExistingNumberDualStack:
    """Verify reserve_existing_number validates against the correct provider."""

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_reserve_livekit_number_checks_dispatch_rule(
        self, mock_twilio_cls, mock_vapi_cls, mock_lk_cls
    ):
        """Reserving a LiveKit number checks for dispatch rule via API."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
            },
        ):
            service = NumberService()

        # Twilio says number exists
        mock_number_details = MagicMock()
        mock_number_details.sid = "PN123"
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        # LiveKit API says dispatch rule exists
        service._livekit_client.has_dispatch_rule.return_value = True

        # Not associated with any project
        mock_session = MagicMock()
        with patch(
            "services.number_service._implementation.ProjectRepository"
        ) as mock_project_repo:
            mock_project_repo.return_value.get_projects_by_phone_number.return_value = (
                []
            )

            # Mock Vapi for _update_vapi_phone_number_name
            service.vapi_client.phone_numbers.list.return_value = []

            result = service.reserve_existing_number(
                "+15551234567", "TestBiz", mock_session, voice_provider="livekit"
            )

        assert result is True
        # Should have checked LiveKit API
        service._livekit_client.has_dispatch_rule.assert_called_once_with(
            "+15551234567"
        )

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_reserve_livekit_number_without_dispatch_rule_raises(
        self, mock_twilio_cls, mock_vapi_cls, mock_lk_cls
    ):
        """Reserving a number for LiveKit that has no dispatch rule raises ValueError."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
            },
        ):
            service = NumberService()

        mock_number_details = MagicMock()
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        # LiveKit API says no dispatch rule
        service._livekit_client.has_dispatch_rule.return_value = False

        mock_session = MagicMock()

        with pytest.raises(ValueError, match="not provisioned for LiveKit"):
            service.reserve_existing_number(
                "+15551234567", "TestBiz", mock_session, voice_provider="livekit"
            )


class TestAssignPhoneNumberToProjectDualStack:
    """Verify assign_phone_number_to_project passes voice_provider through."""

    @patch("services.number_service._implementation.LiveKitSIPClient")
    @patch("services.number_service._implementation.Vapi")
    @patch("services.number_service._implementation.Client")
    def test_assign_passes_voice_provider_to_setup(
        self, mock_twilio_cls, mock_vapi_cls, mock_lk_cls
    ):
        """voice_provider='livekit' is passed through to setup_number."""
        from services.number_service._implementation import NumberService
        from services.number_service._utils import NumberChannel

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "VAPI_API_KEY": "vapi_key",
                "TWILIO_SIP_TRUNK_SID": "TK-trunk",
            },
        ):
            service = NumberService()

        service._livekit_client.is_configured.return_value = True
        service._livekit_client.create_dispatch_rule.return_value = (
            LiveKitProvisionResult(trunk_id="trunk", dispatch_rule_id="DR-assign")
        )

        mock_twilio_number = MagicMock()
        mock_twilio_number.phone_number = "+15559990000"
        mock_twilio_number.sid = "PN-assign"
        service.twilio_client.available_phone_numbers.return_value.toll_free.list.return_value = [
            mock_twilio_number
        ]
        service.twilio_client.incoming_phone_numbers.create.return_value = (
            mock_twilio_number
        )

        mock_number_details = MagicMock()
        mock_number_details.phone_number = "+15559990000"
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        mock_session = MagicMock()

        with patch(
            "services.number_service._implementation.ProjectRepository"
        ) as mock_project_repo:
            mock_project = MagicMock()
            mock_project.channel_identifiers = []
            mock_project_repo.return_value.get_project.return_value = mock_project
            mock_project_repo.return_value.update_project.return_value = mock_project

            result = service.assign_phone_number_to_project(
                project_id=uuid.uuid4(),
                project_name="TestProject",
                channels=[NumberChannel.VOICE],
                session=mock_session,
                context=MagicMock(),
                voice_provider="livekit",
            )

        assert result == "+15559990000"
        # Vapi should NOT have been called
        service.vapi_client.phone_numbers.create.assert_not_called()
        # LiveKit dispatch rule should have been created
        service._livekit_client.create_dispatch_rule.assert_called_once()
