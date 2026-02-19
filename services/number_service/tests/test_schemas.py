# pyright: reportCallIssue=false
"""Tests for phone number API schemas with voice_provider support.

Verifies backward compatibility and correct defaults for dual-stack provisioning.
"""

from api.schemas.admin.phone_number import PhoneNumberInfo, ReserveProjectNumberRequest
from services.number_service._utils import NumberChannel


class TestReserveProjectNumberRequestDefaults:
    """Verify ReserveProjectNumberRequest backward compatibility."""

    def test_voice_provider_defaults_to_vapi(self):
        """Not passing voice_provider defaults to 'vapi' for backward compatibility."""
        request = ReserveProjectNumberRequest(
            channels=[NumberChannel.VOICE],
        )
        assert request.voice_provider == "vapi"

    def test_voice_provider_can_be_set_to_livekit(self):
        """Explicitly setting voice_provider to 'livekit' is accepted."""
        request = ReserveProjectNumberRequest(
            channels=[NumberChannel.VOICE],
            voice_provider="livekit",
        )
        assert request.voice_provider == "livekit"


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

    def test_voice_provider_set_to_vapi(self):
        """voice_provider can be set to vapi."""
        info = PhoneNumberInfo(
            phone_number="+15551234567",
            sid="PN123",
            voice_provider="vapi",
        )
        assert info.voice_provider == "vapi"
