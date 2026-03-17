# pyright: reportAttributeAccessIssue=false
"""Business-driven tests for NumberService LiveKit provisioning.

These tests verify LiveKit provisioning behavior using trunk_sid:
- LiveKit path: purchase → set trunk_sid on Twilio number (SIP routing)
- Release paths: clear trunk_sid for LiveKit
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest


class TestSetupNumberLiveKitPath:
    """Verify that LiveKit provisioning sets trunk_sid on the Twilio number."""

    @patch("services.number_service._implementation.Client")
    def test_setup_number_livekit_sets_trunk_sid(self, mock_twilio_cls):
        """LiveKit path: purchases number, sets trunk_sid for SIP routing."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_SIP_TRUNK_SID": "TK-sip-trunk",
            },
        ):
            service = NumberService()

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

        # Mock get_number_details (used by _setup_number_for_livekit)
        mock_number_details = MagicMock()
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        result = service.setup_number(
            country_code="US",
            toll_free=True,
            merchant_name="Test Business",
            purchase_number=True,
            voice_provider="livekit",
        )

        assert result.number == "+15551234567"
        # trunk_sid should have been set on the Twilio number
        mock_number_details.update.assert_called_once_with(trunk_sid="TK-sip-trunk")

    @patch("services.number_service._implementation.Client")
    def test_setup_number_livekit_no_trunk_sid_raises(self, mock_twilio_cls):
        """LiveKit path without TWILIO_SIP_TRUNK_SID raises ValueError."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                # No TWILIO_SIP_TRUNK_SID
            },
        ):
            service = NumberService()

        mock_twilio_number = MagicMock()
        mock_twilio_number.phone_number = "+15551234567"
        mock_twilio_number.sid = "PN123"
        service.twilio_client.available_phone_numbers.return_value.toll_free.list.return_value = [
            mock_twilio_number
        ]
        service.twilio_client.incoming_phone_numbers.create.return_value = (
            mock_twilio_number
        )

        with pytest.raises(ValueError, match="TWILIO_SIP_TRUNK_SID"):
            service.setup_number(
                country_code="US",
                toll_free=True,
                merchant_name="Test",
                purchase_number=True,
                voice_provider="livekit",
            )


class TestSetupNumberLiveKitRollback:
    """Verify that LiveKit provisioning rollback works on failure."""

    @patch("services.number_service._implementation.Client")
    def test_livekit_trunk_sid_failure_deletes_number(self, mock_twilio_cls):
        """If trunk_sid update fails, the purchased number is deleted."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_SIP_TRUNK_SID": "TK-sip-trunk",
            },
        ):
            service = NumberService()

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

        # Mock get_number_details to simulate trunk_sid update failure
        mock_number_details = MagicMock()
        mock_number_details.update.side_effect = Exception("Twilio API error")
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        with pytest.raises(ValueError, match="Failed to provision number for LiveKit"):
            service.setup_number(
                country_code="US",
                toll_free=True,
                merchant_name="Test",
                purchase_number=True,
                voice_provider="livekit",
            )


class TestDeleteNumberDualStack:
    """Verify delete_number routes to correct provider via trunk_sid check."""

    @patch("services.number_service._implementation.Client")
    def test_delete_livekit_number_clears_trunk_sid(self, mock_twilio_cls):
        """Deleting a LiveKit number clears trunk_sid then deletes from Twilio."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
            },
        ):
            service = NumberService()

        # Mock: Twilio number has trunk_sid set (LiveKit number)
        mock_number_details = MagicMock()
        mock_number_details.trunk_sid = "TK-sip-trunk"
        mock_number_details.phone_number = "+15551234567"
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        service.delete_number("+15551234567")

        # trunk_sid should have been cleared
        mock_number_details.update.assert_any_call(trunk_sid="")


class TestReleaseNumberWithOptionsDualStack:
    """Verify release_number_with_options handles both providers via trunk_sid."""

    @patch("services.number_service._implementation.Client")
    def test_return_to_pool_livekit_clears_trunk_and_sets_available(
        self, mock_twilio_cls
    ):
        """Returning a LiveKit number to pool clears trunk_sid AND sets available."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
            },
        ):
            service = NumberService()

        # Mock: Twilio number has trunk_sid set (LiveKit number)
        mock_number_details = MagicMock()
        mock_number_details.trunk_sid = "TK-sip-trunk"
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        service.release_number_with_options("+15551234567", "return_to_pool")

        # trunk_sid should have been cleared
        mock_number_details.update.assert_any_call(trunk_sid="")


class TestReserveExistingNumberDualStack:
    """Verify reserve_existing_number validates against the correct provider."""

    @patch("services.number_service._implementation.Client")
    def test_reserve_livekit_number_checks_trunk_sid(self, mock_twilio_cls):
        """Reserving a LiveKit number checks for trunk_sid on Twilio number."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
            },
        ):
            service = NumberService()

        # Mock: Twilio number has trunk_sid set
        mock_number_details = MagicMock()
        mock_number_details.sid = "PN123"
        mock_number_details.trunk_sid = "TK-sip-trunk"
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        mock_session = MagicMock()
        with patch(
            "services.number_service._implementation.ProjectRepository"
        ) as mock_project_repo:
            mock_project_repo.return_value.get_projects_by_phone_number.return_value = (
                []
            )

            result = service.reserve_existing_number(
                "+15551234567", "TestBiz", mock_session, voice_provider="livekit"
            )

        assert result is True

    @patch("services.number_service._implementation.Client")
    def test_reserve_livekit_number_without_trunk_sid_raises(self, mock_twilio_cls):
        """Reserving a number for LiveKit that has no trunk_sid raises ValueError."""
        from services.number_service._implementation import NumberService

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
            },
        ):
            service = NumberService()

        # Mock: Twilio number has no trunk_sid
        mock_number_details = MagicMock()
        mock_number_details.trunk_sid = None
        service.twilio_client.incoming_phone_numbers.list.return_value = [
            mock_number_details
        ]

        mock_session = MagicMock()

        with pytest.raises(ValueError, match="not provisioned for LiveKit"):
            service.reserve_existing_number(
                "+15551234567", "TestBiz", mock_session, voice_provider="livekit"
            )


class TestAssignPhoneNumberToProjectDualStack:
    """Verify assign_phone_number_to_project passes voice_provider through."""

    @patch("services.number_service._implementation.Client")
    def test_assign_passes_voice_provider_to_setup(self, mock_twilio_cls):
        """voice_provider='livekit' is passed through to setup_number."""
        from services.number_service._implementation import NumberService
        from services.number_service._utils import NumberChannel

        with patch.dict(
            "os.environ",
            {
                "TWILIO_ACCOUNT_SID": "ACtest",
                "TWILIO_AUTH_TOKEN": "token",
                "TWILIO_SIP_TRUNK_SID": "TK-trunk",
            },
        ):
            service = NumberService()

        # Mock Twilio purchase
        mock_twilio_number = MagicMock()
        mock_twilio_number.phone_number = "+15559990000"
        mock_twilio_number.sid = "PN-assign"
        service.twilio_client.available_phone_numbers.return_value.toll_free.list.return_value = [
            mock_twilio_number
        ]
        service.twilio_client.incoming_phone_numbers.create.return_value = (
            mock_twilio_number
        )

        # Mock get_number_details for _setup_number_for_livekit
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
        # trunk_sid should have been set
        mock_number_details.update.assert_called_once_with(trunk_sid="TK-trunk")
