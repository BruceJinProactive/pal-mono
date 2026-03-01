# pyright: reportGeneralTypeIssues=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportCallIssue=false
"""Tests for LiveKitTransferTool — cold transfer via SIP REFER."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from livekit import api as livekit_api

from agent.tool import ToolMetadata
from tools.livekit_transfer_tool._implementation import (
    LiveKitTransferTool,
    _mask_phone,
    _normalize_phone_to_e164,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metadata(**overrides) -> ToolMetadata:
    defaults = {
        "agent_id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "account_name": "Test Account",
        "user_id": uuid.uuid4(),
        "session_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "timezone": "America/New_York",
        "customer_phone": "+15551111111",
        "store_phone": "+15552222222",
        "channel": "voice",
    }
    defaults.update(overrides)
    return ToolMetadata(**defaults)


def _make_lk_api() -> MagicMock:
    """Create a mock LiveKitAPI with an async SIP service."""
    mock_api = MagicMock(spec=livekit_api.LiveKitAPI)
    mock_sip = MagicMock()
    mock_sip.transfer_sip_participant = AsyncMock(
        return_value=livekit_api.SIPParticipantInfo(
            participant_id="part-123",
            participant_identity="sip-caller",
            room_name="call-room-1",
            sip_call_id="call-abc",
        )
    )
    mock_api.sip = mock_sip
    return mock_api


def _make_tool(
    destinations: dict[str, str] | None = None,
    transfer_message: str | None = None,
    show_agent_caller_id: bool = False,
    lk_api: MagicMock | None = None,
    room_name: str | None = "call-room-1",
    participant_identity: str | None = "sip-caller",
    metadata_overrides: dict | None = None,
) -> LiveKitTransferTool:
    """Create a LiveKitTransferTool with sensible defaults for testing."""
    if destinations is None:
        destinations = {"general": "+15559876543"}
    if lk_api is None:
        lk_api = _make_lk_api()
    meta = _make_metadata(**(metadata_overrides or {}))
    return LiveKitTransferTool(
        tool_metadata=meta,
        transfer_destinations=destinations,
        transfer_message=transfer_message,
        show_agent_caller_id=show_agent_caller_id,
        lk_api=lk_api,
        room_name=room_name,
        participant_identity=participant_identity,
    )


# ---------------------------------------------------------------------------
# Unit tests: _mask_phone
# ---------------------------------------------------------------------------


class TestMaskPhone:
    def test_masks_full_number(self) -> None:
        assert _mask_phone("+15551234567") == "***4567"

    def test_masks_short_number(self) -> None:
        assert _mask_phone("1234") == "****"

    def test_masks_none(self) -> None:
        assert _mask_phone(None) == "None"

    def test_masks_empty_string(self) -> None:
        assert _mask_phone("") == "None"


# ---------------------------------------------------------------------------
# Unit tests: _normalize_phone_to_e164
# ---------------------------------------------------------------------------


class TestNormalizePhoneToE164:
    def test_keeps_e164(self) -> None:
        assert _normalize_phone_to_e164("+16468761234") == "+16468761234"

    def test_formats_us_10_digit(self) -> None:
        assert _normalize_phone_to_e164("(646) 876-1234") == "+16468761234"

    def test_formats_us_11_digit_leading_1(self) -> None:
        assert _normalize_phone_to_e164("1 (646) 876-1234") == "+16468761234"

    def test_formats_tel_uri(self) -> None:
        assert _normalize_phone_to_e164("tel:(646) 876-1234") == "+16468761234"

    def test_converts_00_prefix_to_plus(self) -> None:
        assert _normalize_phone_to_e164("00442079460056") == "+442079460056"

    def test_strips_extension_suffix(self) -> None:
        assert _normalize_phone_to_e164("+1 (646) 876-1234 ext 99") == "+16468761234"

    def test_strips_extension_attached_to_digits(self) -> None:
        assert _normalize_phone_to_e164("+16468761234ext123") == "+16468761234"

    def test_rejects_invalid_text(self) -> None:
        with pytest.raises(ValueError):
            _normalize_phone_to_e164("call me maybe")

    def test_rejects_short_number(self) -> None:
        with pytest.raises(ValueError):
            _normalize_phone_to_e164("12345")


# ---------------------------------------------------------------------------
# Unit tests: _get_destination_for_purpose
# ---------------------------------------------------------------------------


class TestGetDestinationForPurpose:
    def test_exact_match(self) -> None:
        tool = _make_tool(
            destinations={"complaint": "+15550001111", "general": "+15559876543"}
        )
        assert tool._get_destination_for_purpose("complaint") == "+15550001111"

    def test_falls_back_to_general(self) -> None:
        tool = _make_tool(destinations={"general": "+15559876543"})
        assert tool._get_destination_for_purpose("complaint") == "+15559876543"

    def test_returns_none_when_no_match_and_no_general(self) -> None:
        tool = _make_tool(destinations={"faq": "+15550001111"})
        assert tool._get_destination_for_purpose("complaint") is None

    def test_returns_none_for_empty_destinations(self) -> None:
        tool = _make_tool(destinations={})
        assert tool._get_destination_for_purpose("general") is None


# ---------------------------------------------------------------------------
# Unit tests: _build_transfer_to
# ---------------------------------------------------------------------------


class TestBuildTransferTo:
    def test_phone_number_gets_tel_prefix(self) -> None:
        tool = _make_tool()
        assert tool._build_transfer_to("+15559876543") == "tel:+15559876543"

    def test_formatted_phone_number_is_normalized(self) -> None:
        tool = _make_tool()
        assert tool._build_transfer_to("(646) 876-1234") == "tel:+16468761234"

    def test_tel_uri_phone_number_is_normalized(self) -> None:
        tool = _make_tool()
        assert tool._build_transfer_to("tel:(646) 876-1234") == "tel:+16468761234"

    def test_sip_uri_passed_through(self) -> None:
        tool = _make_tool()
        assert (
            tool._build_transfer_to("sip:+15559876543@sip.provider.com")
            == "sip:+15559876543@sip.provider.com"
        )

    def test_sip_uri_case_insensitive(self) -> None:
        tool = _make_tool()
        assert (
            tool._build_transfer_to("SIP:+15559876543@sip.provider.com")
            == "SIP:+15559876543@sip.provider.com"
        )


# ---------------------------------------------------------------------------
# Integration tests: call_transfer — success paths
# ---------------------------------------------------------------------------


class TestCallTransferSuccess:
    @pytest.mark.asyncio
    async def test_basic_phone_transfer(self) -> None:
        """Basic cold transfer to a phone number succeeds."""
        tool = _make_tool(destinations={"general": "+15559876543"})
        result = await tool.call_transfer(purpose="general")

        assert result == "Call has been transferred"
        tool.lk_api.sip.transfer_sip_participant.assert_awaited_once()

        # Verify the request passed to LiveKit
        call_args = tool.lk_api.sip.transfer_sip_participant.call_args
        request = call_args[0][0]
        assert isinstance(request, livekit_api.TransferSIPParticipantRequest)
        assert request.participant_identity == "sip-caller"
        assert request.room_name == "call-room-1"
        assert request.transfer_to == "tel:+15559876543"
        assert request.play_dialtone is True

    @pytest.mark.asyncio
    async def test_sip_uri_transfer(self) -> None:
        """Cold transfer to a SIP URI passes the URI through directly."""
        tool = _make_tool(destinations={"general": "sip:+15559876543@sip.provider.com"})
        result = await tool.call_transfer(purpose="general")

        assert result == "Call has been transferred"
        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.transfer_to == "sip:+15559876543@sip.provider.com"

    @pytest.mark.asyncio
    async def test_purpose_fallback_to_general(self) -> None:
        """When requested purpose not found, falls back to general."""
        tool = _make_tool(destinations={"general": "+15559876543"})
        result = await tool.call_transfer(purpose="complaint")

        assert result == "Call has been transferred"
        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.transfer_to == "tel:+15559876543"

    @pytest.mark.asyncio
    async def test_exact_purpose_match(self) -> None:
        """When exact purpose exists, uses that destination."""
        tool = _make_tool(
            destinations={
                "complaint": "+15550001111",
                "general": "+15559876543",
            }
        )
        result = await tool.call_transfer(purpose="complaint")

        assert result == "Call has been transferred"
        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.transfer_to == "tel:+15550001111"

    @pytest.mark.asyncio
    async def test_default_purpose_is_general(self) -> None:
        """Calling with no purpose argument defaults to 'general'."""
        tool = _make_tool(destinations={"general": "+15559876543"})
        result = await tool.call_transfer()

        assert result == "Call has been transferred"

    @pytest.mark.asyncio
    async def test_play_dialtone_enabled(self) -> None:
        """Dialtone is enabled during transfer."""
        tool = _make_tool()
        await tool.call_transfer()

        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.play_dialtone is True

    @pytest.mark.asyncio
    async def test_formatted_phone_transfer_is_normalized(self) -> None:
        """Formatted destination is normalized to E.164 before transfer."""
        tool = _make_tool(destinations={"general": "(646) 876-1234"})

        result = await tool.call_transfer()

        assert result == "Call has been transferred"
        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.transfer_to == "tel:+16468761234"


# ---------------------------------------------------------------------------
# Integration tests: call_transfer — caller ID headers
# ---------------------------------------------------------------------------


class TestCallTransferCallerID:
    @pytest.mark.asyncio
    async def test_default_sends_customer_phone_header(self) -> None:
        """Default (show_agent_caller_id=False) sends customer phone as caller ID."""
        tool = _make_tool(show_agent_caller_id=False)
        await tool.call_transfer()

        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.headers.get("X-Caller-ID") == "+15551111111"

    @pytest.mark.asyncio
    async def test_agent_caller_id_sends_store_phone_header(self) -> None:
        """show_agent_caller_id=True sends store phone as caller ID."""
        tool = _make_tool(show_agent_caller_id=True)
        await tool.call_transfer()

        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.headers.get("X-Caller-ID") == "+15552222222"

    @pytest.mark.asyncio
    async def test_no_customer_phone_omits_header(self) -> None:
        """No customer phone → no caller ID header set."""
        tool = _make_tool(
            show_agent_caller_id=False,
            metadata_overrides={"customer_phone": None},
        )
        await tool.call_transfer()

        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert "X-Caller-ID" not in request.headers

    @pytest.mark.asyncio
    async def test_no_store_phone_omits_header(self) -> None:
        """show_agent_caller_id=True but no store phone → no header."""
        tool = _make_tool(
            show_agent_caller_id=True,
            metadata_overrides={"store_phone": None},
        )
        await tool.call_transfer()

        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert "X-Caller-ID" not in request.headers


# ---------------------------------------------------------------------------
# Integration tests: call_transfer — validation errors
# ---------------------------------------------------------------------------


class TestCallTransferValidation:
    @pytest.mark.asyncio
    async def test_non_voice_channel_rejected(self) -> None:
        """Non-voice channel returns error without calling LiveKit."""
        tool = _make_tool(metadata_overrides={"channel": "sms"})
        result = await tool.call_transfer()

        assert "only available for voice calls" in result
        tool.lk_api.sip.transfer_sip_participant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_web_channel_rejected(self) -> None:
        """Web channel returns error without calling LiveKit."""
        tool = _make_tool(metadata_overrides={"channel": "web"})
        result = await tool.call_transfer()

        assert "only available for voice calls" in result
        tool.lk_api.sip.transfer_sip_participant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_destination_configured(self) -> None:
        """No destination for purpose and no general fallback returns error."""
        tool = _make_tool(destinations={})
        result = await tool.call_transfer(purpose="complaint")

        assert "No transfer destination configured" in result
        tool.lk_api.sip.transfer_sip_participant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_phone_destination_rejected_before_livekit(self) -> None:
        """Invalid non-SIP destination fails before hitting LiveKit."""
        tool = _make_tool(destinations={"general": "not-a-phone-number"})
        result = await tool.call_transfer()

        assert "Invalid transfer destination format" in result
        tool.lk_api.sip.transfer_sip_participant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_lk_api(self) -> None:
        """Missing LiveKit API client returns error."""
        tool = _make_tool(lk_api=MagicMock(spec=None))
        tool.lk_api = None
        result = await tool.call_transfer()

        assert "LiveKit API client is not available" in result

    @pytest.mark.asyncio
    async def test_missing_room_name(self) -> None:
        """Missing room name returns error."""
        tool = _make_tool(room_name=None)
        result = await tool.call_transfer()

        assert "room or participant info is not available" in result
        tool.lk_api.sip.transfer_sip_participant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_participant_identity(self) -> None:
        """Missing participant identity returns error."""
        tool = _make_tool(participant_identity=None)
        result = await tool.call_transfer()

        assert "room or participant info is not available" in result
        tool.lk_api.sip.transfer_sip_participant.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_both_room_and_participant(self) -> None:
        """Missing both room and participant returns error."""
        tool = _make_tool(room_name=None, participant_identity=None)
        result = await tool.call_transfer()

        assert "room or participant info is not available" in result

    @pytest.mark.asyncio
    async def test_none_channel_allows_transfer(self) -> None:
        """None channel (unset) does not block transfer."""
        tool = _make_tool(metadata_overrides={"channel": None})
        result = await tool.call_transfer()

        assert result == "Call has been transferred"

    @pytest.mark.asyncio
    async def test_voice_channel_allows_transfer(self) -> None:
        """Explicit voice channel allows transfer."""
        tool = _make_tool(metadata_overrides={"channel": "voice"})
        result = await tool.call_transfer()

        assert result == "Call has been transferred"


# ---------------------------------------------------------------------------
# Integration tests: call_transfer — LiveKit API errors
# ---------------------------------------------------------------------------


class TestCallTransferErrors:
    @pytest.mark.asyncio
    async def test_participant_not_found_returns_call_ended(self) -> None:
        """TwirpError NOT_FOUND → graceful 'call has already ended' message."""
        lk = _make_lk_api()
        lk.sip.transfer_sip_participant = AsyncMock(
            side_effect=livekit_api.TwirpError(
                code=livekit_api.TwirpErrorCode.NOT_FOUND,
                msg="participant not found",
                status=404,
            )
        )
        tool = _make_tool(lk_api=lk)
        result = await tool.call_transfer()

        assert result == "Call has already ended. Transfer is no longer possible."

    @pytest.mark.asyncio
    async def test_twirp_internal_error(self) -> None:
        """TwirpError INTERNAL → error message returned."""
        lk = _make_lk_api()
        lk.sip.transfer_sip_participant = AsyncMock(
            side_effect=livekit_api.TwirpError(
                code=livekit_api.TwirpErrorCode.INTERNAL,
                msg="internal server error",
                status=500,
            )
        )
        tool = _make_tool(lk_api=lk)
        result = await tool.call_transfer()

        assert "LiveKit API error" in result
        assert "internal server error" in result

    @pytest.mark.asyncio
    async def test_twirp_unavailable_error(self) -> None:
        """TwirpError UNAVAILABLE → error message returned."""
        lk = _make_lk_api()
        lk.sip.transfer_sip_participant = AsyncMock(
            side_effect=livekit_api.TwirpError(
                code=livekit_api.TwirpErrorCode.UNAVAILABLE,
                msg="service unavailable",
                status=503,
            )
        )
        tool = _make_tool(lk_api=lk)
        result = await tool.call_transfer()

        assert "LiveKit API error" in result

    @pytest.mark.asyncio
    async def test_twirp_permission_denied(self) -> None:
        """TwirpError PERMISSION_DENIED → error message returned."""
        lk = _make_lk_api()
        lk.sip.transfer_sip_participant = AsyncMock(
            side_effect=livekit_api.TwirpError(
                code=livekit_api.TwirpErrorCode.PERMISSION_DENIED,
                msg="permission denied",
                status=403,
            )
        )
        tool = _make_tool(lk_api=lk)
        result = await tool.call_transfer()

        assert "LiveKit API error" in result
        assert "permission denied" in result

    @pytest.mark.asyncio
    async def test_twirp_invalid_argument(self) -> None:
        """TwirpError INVALID_ARGUMENT → error message returned."""
        lk = _make_lk_api()
        lk.sip.transfer_sip_participant = AsyncMock(
            side_effect=livekit_api.TwirpError(
                code=livekit_api.TwirpErrorCode.INVALID_ARGUMENT,
                msg="invalid transfer_to",
                status=400,
            )
        )
        tool = _make_tool(lk_api=lk)
        result = await tool.call_transfer()

        assert "LiveKit API error" in result
        assert "invalid transfer_to" in result

    @pytest.mark.asyncio
    async def test_unexpected_exception(self) -> None:
        """Unexpected exception → generic error message returned."""
        lk = _make_lk_api()
        lk.sip.transfer_sip_participant = AsyncMock(
            side_effect=RuntimeError("connection reset")
        )
        tool = _make_tool(lk_api=lk)
        result = await tool.call_transfer()

        assert "Unexpected error" in result
        assert "connection reset" in result

    @pytest.mark.asyncio
    async def test_timeout_exception(self) -> None:
        """Timeout during transfer → error message returned."""
        import asyncio

        lk = _make_lk_api()
        lk.sip.transfer_sip_participant = AsyncMock(side_effect=asyncio.TimeoutError())
        tool = _make_tool(lk_api=lk)
        result = await tool.call_transfer()

        assert "Unexpected error" in result


# ---------------------------------------------------------------------------
# Integration tests: call_transfer — constructor defaults
# ---------------------------------------------------------------------------


class TestConstructorDefaults:
    def test_default_transfer_message(self) -> None:
        tool = _make_tool(transfer_message=None)
        assert (
            tool.transfer_message
            == "I'll transfer you to our team. Just hang tight for a moment."
        )

    def test_custom_transfer_message(self) -> None:
        tool = _make_tool(transfer_message="Please hold while I connect you.")
        assert tool.transfer_message == "Please hold while I connect you."

    def test_default_show_agent_caller_id(self) -> None:
        tool = _make_tool()
        assert tool.show_agent_caller_id is False

    def test_destination_number_creates_general_destination(self) -> None:
        """destination_number shorthand populates transfer_destinations."""
        meta = _make_metadata()
        tool = LiveKitTransferTool(
            tool_metadata=meta,
            destination_number="+16468761234",
            lk_api=_make_lk_api(),
            room_name="room-1",
            participant_identity="sip-caller",
        )
        assert tool.transfer_destinations == {"general": "+16468761234"}

    def test_transfer_destinations_takes_precedence_over_destination_number(
        self,
    ) -> None:
        """Explicit transfer_destinations wins over destination_number."""
        meta = _make_metadata()
        tool = LiveKitTransferTool(
            tool_metadata=meta,
            transfer_destinations={"complaint": "+15550001111"},
            destination_number="+16468761234",
            lk_api=_make_lk_api(),
            room_name="room-1",
            participant_identity="sip-caller",
        )
        assert tool.transfer_destinations == {"complaint": "+15550001111"}

    def test_neither_destinations_nor_number_gives_empty_dict(self) -> None:
        """No destinations and no destination_number → empty dict."""
        meta = _make_metadata()
        tool = LiveKitTransferTool(
            tool_metadata=meta,
            lk_api=_make_lk_api(),
            room_name="room-1",
            participant_identity="sip-caller",
        )
        assert tool.transfer_destinations == {}

    def test_ignores_unknown_kwargs(self) -> None:
        """Unknown kwargs from raw_config are accepted and ignored."""
        meta = _make_metadata()
        tool = LiveKitTransferTool(
            tool_metadata=meta,
            transfer_destinations={"general": "+15559876543"},
            lk_api=_make_lk_api(),
            room_name="room-1",
            participant_identity="sip-caller",
            some_unknown_arg="should not raise",
            another_arg=42,
        )
        assert tool.room_name == "room-1"

    def test_tool_name_is_livekit_transfer_tool(self) -> None:
        tool = _make_tool()
        assert tool.name == "livekit_transfer_tool"


# ---------------------------------------------------------------------------
# Integration tests: multiple destinations
# ---------------------------------------------------------------------------


class TestMultipleDestinations:
    @pytest.mark.asyncio
    async def test_complaint_purpose(self) -> None:
        tool = _make_tool(
            destinations={
                "general": "+15559876543",
                "complaint": "+15550001111",
                "faq": "+15550002222",
                "catering": "+15550003333",
            }
        )
        await tool.call_transfer(purpose="complaint")

        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.transfer_to == "tel:+15550001111"

    @pytest.mark.asyncio
    async def test_faq_purpose(self) -> None:
        tool = _make_tool(
            destinations={
                "general": "+15559876543",
                "faq": "+15550002222",
            }
        )
        await tool.call_transfer(purpose="faq")

        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.transfer_to == "tel:+15550002222"

    @pytest.mark.asyncio
    async def test_catering_purpose(self) -> None:
        tool = _make_tool(
            destinations={
                "general": "+15559876543",
                "catering": "sip:catering@sip.provider.com",
            }
        )
        await tool.call_transfer(purpose="catering")

        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.transfer_to == "sip:catering@sip.provider.com"

    @pytest.mark.asyncio
    async def test_unknown_purpose_falls_back_to_general(self) -> None:
        tool = _make_tool(
            destinations={
                "general": "+15559876543",
                "complaint": "+15550001111",
            }
        )
        await tool.call_transfer(purpose="billing")

        request = tool.lk_api.sip.transfer_sip_participant.call_args[0][0]
        assert request.transfer_to == "tel:+15559876543"

    @pytest.mark.asyncio
    async def test_unknown_purpose_no_general_returns_error(self) -> None:
        tool = _make_tool(destinations={"complaint": "+15550001111"})
        result = await tool.call_transfer(purpose="billing")

        assert "No transfer destination configured" in result
        tool.lk_api.sip.transfer_sip_participant.assert_not_awaited()
