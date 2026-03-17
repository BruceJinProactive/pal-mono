# pyright: reportCallIssue=false
"""Tests for phone number API schemas with voice_provider support.

Verifies LiveKit provisioning for phone numbers.
"""

from api.schemas.admin.phone_number import (
    PhoneNumberInfo,
    PurchaseNumberRequest,
    ReserveProjectNumberRequest,
)
from services.number_service._utils import NumberChannel


class TestReserveProjectNumberRequestDefaults:
    """Verify ReserveProjectNumberRequest defaults."""

    def test_voice_provider_can_be_set_to_livekit(self):
        """Explicitly setting voice_provider to 'livekit' is accepted."""
        request = ReserveProjectNumberRequest(
            channels=[NumberChannel.VOICE],
            voice_provider="livekit",
        )
        assert request.voice_provider == "livekit"


class TestPurchaseNumberRequestDefaults:
    """Verify PurchaseNumberRequest voice_provider defaults."""

    def test_voice_provider_can_be_set_to_livekit(self):
        """Explicitly setting voice_provider to 'livekit' is accepted."""
        request = PurchaseNumberRequest(voice_provider="livekit")
        assert request.voice_provider == "livekit"

    def test_other_defaults_unchanged(self):
        """Verify existing field defaults."""
        request = PurchaseNumberRequest()
        assert request.country_code == "US"
        assert request.toll_free is False
        assert request.area_code is None
        assert request.contains is None


class TestPhoneNumberInfoVoiceProvider:
    """Verify PhoneNumberInfo includes optional voice_provider."""

    def test_voice_provider_none_by_default(self):
        """voice_provider is None when not provided."""
        info = PhoneNumberInfo(
            phone_number="+15551234567",
            sid="PN123",
        )
        assert info.voice_provider is None

    def test_voice_provider_set_to_livekit(self):
        """voice_provider can be set to livekit."""
        info = PhoneNumberInfo(
            phone_number="+15551234567",
            sid="PN123",
            voice_provider="livekit",
        )
        assert info.voice_provider == "livekit"
