# pyright: reportGeneralTypeIssues=false, reportAttributeAccessIssue=false
"""Tests for _parse_caller_info in chat_completions.

Validates extraction of sender_identifier, recipient_identifier, call_id,
room_name, and participant_identity from the model JSON string.
"""

import json

from api.routes.chat.chat_completions import _parse_caller_info

# ---------------------------------------------------------------------------
# LiveKit field extraction
# ---------------------------------------------------------------------------


class TestParseCallerInfoLiveKit:
    """Tests for LiveKit-specific fields in _parse_caller_info."""

    def test_extracts_room_name_and_participant_identity(self) -> None:
        """LiveKit caller_info with both fields returns them correctly."""
        model = json.dumps(
            {
                "sender_identifier": "+15551111111",
                "recipient_identifier": "+15552222222",
                "call_id": "call-123",
                "room_name": "room-abc",
                "participant_identity": "participant-xyz",
            }
        )
        sender, recipient, call_id, room_name, participant_identity = (
            _parse_caller_info(model)
        )
        assert room_name == "room-abc"
        assert participant_identity == "participant-xyz"

    def test_missing_room_name_returns_none(self) -> None:
        """caller_info without room_name returns None for room_name."""
        model = json.dumps(
            {
                "sender_identifier": "+15551111111",
                "recipient_identifier": "+15552222222",
                "participant_identity": "participant-xyz",
            }
        )
        _, _, _, room_name, participant_identity = _parse_caller_info(model)
        assert room_name is None
        assert participant_identity == "participant-xyz"

    def test_missing_participant_identity_returns_none(self) -> None:
        """caller_info without participant_identity returns None for it."""
        model = json.dumps(
            {
                "sender_identifier": "+15551111111",
                "recipient_identifier": "+15552222222",
                "room_name": "room-abc",
            }
        )
        _, _, _, room_name, participant_identity = _parse_caller_info(model)
        assert room_name == "room-abc"
        assert participant_identity is None

    def test_missing_both_livekit_fields_returns_none(self) -> None:
        """Caller info without LiveKit fields returns None for both room and participant."""
        model = json.dumps(
            {
                "sender_identifier": "+15551111111",
                "recipient_identifier": "+15552222222",
                "call_id": "call-123",
            }
        )
        _, _, _, room_name, participant_identity = _parse_caller_info(model)
        assert room_name is None
        assert participant_identity is None

    def test_existing_fields_still_parsed(self) -> None:
        """sender_identifier, recipient_identifier, call_id extracted alongside LiveKit fields."""
        model = json.dumps(
            {
                "sender_identifier": "+15551111111",
                "recipient_identifier": "+15552222222",
                "call_id": "call-456",
                "room_name": "room-abc",
                "participant_identity": "participant-xyz",
            }
        )
        sender, recipient, call_id, room_name, participant_identity = (
            _parse_caller_info(model)
        )
        assert sender == "+15551111111"
        assert recipient == "+15552222222"
        assert call_id == "call-456"
        assert room_name == "room-abc"
        assert participant_identity == "participant-xyz"

    def test_empty_string_livekit_fields(self) -> None:
        """Empty string values are returned as empty strings (not None)."""
        model = json.dumps(
            {
                "sender_identifier": "+15551111111",
                "recipient_identifier": "+15552222222",
                "room_name": "",
                "participant_identity": "",
            }
        )
        _, _, _, room_name, participant_identity = _parse_caller_info(model)
        assert room_name == ""
        assert participant_identity == ""
