"""Tests for events.schema module.

Tests cover event serialization, especially the to_detail() method
which handles UUID, datetime, and nested dataclass serialization.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from events.schema import (
    AudioRecordingReference,
    BaseEvent,
    ConversationEvaluationRequested,
    SampleEvent,
)


class TestAudioRecordingReference:
    """Test AudioRecordingReference dataclass."""

    def test_basic_initialization(self):
        """Test creating an AudioRecordingReference with minimal fields."""
        ref = AudioRecordingReference(
            s3_uri="s3://bucket/key.wav",
        )
        assert ref.s3_uri == "s3://bucket/key.wav"
        assert ref.duration_seconds is None

    def test_with_duration(self):
        """Test AudioRecordingReference with duration."""
        ref = AudioRecordingReference(
            s3_uri="s3://bucket/key.mp3",
            duration_seconds=123.45,
        )
        assert ref.s3_uri == "s3://bucket/key.mp3"
        assert ref.duration_seconds == 123.45


class TestBaseEventToDetail:
    """Test BaseEvent.to_detail() serialization."""

    def test_simple_event_serialization(self):
        """Test basic event serialization with simple types."""
        event = SampleEvent(
            message="Hello, world!",
            timestamp=datetime(2024, 3, 12, 10, 30, 0),
        )
        detail = event.to_detail()

        assert detail["detail_type"] == "sample.Message"
        assert detail["message"] == "Hello, world!"
        assert detail["timestamp"] == "2024-03-12T10:30:00"

    def test_uuid_serialization(self):
        """Test UUID fields are converted to strings."""
        conversation_id = uuid4()
        user_id = uuid4()
        account_id = uuid4()
        project_id = uuid4()

        event = ConversationEvaluationRequested(
            conversation_id=conversation_id,
            call_id="call-123",
            user_id=user_id,
            account_id=account_id,
            account_name="test-account",
            project_id=project_id,
            channel="voice",
            is_test=False,
            call_metadata={},
        )

        detail = event.to_detail()

        assert detail["conversation_id"] == str(conversation_id)
        assert detail["user_id"] == str(user_id)
        assert detail["account_id"] == str(account_id)
        assert detail["project_id"] == str(project_id)

    def test_none_values_skipped(self):
        """Test that None values are not included in the output."""
        event = ConversationEvaluationRequested(
            conversation_id=uuid4(),
            call_id="call-123",
            user_id=uuid4(),
            account_id=uuid4(),
            account_name="test-account",
            project_id=uuid4(),
            channel="voice",
            is_test=False,
            call_metadata={},
            audio_recording=None,  # Explicitly None
        )

        detail = event.to_detail()

        # audio_recording should not be in detail when None
        assert "audio_recording" not in detail

    def test_nested_dataclass_serialization(self):
        """Test nested dataclasses are recursively serialized."""
        audio_ref = AudioRecordingReference(
            s3_uri="s3://bucket/recording.wav",
            duration_seconds=42.5,
        )

        event = ConversationEvaluationRequested(
            conversation_id=uuid4(),
            call_id="call-123",
            user_id=uuid4(),
            account_id=uuid4(),
            account_name="test-account",
            project_id=uuid4(),
            channel="voice",
            is_test=False,
            call_metadata={},
            audio_recording=audio_ref,
        )

        detail = event.to_detail()

        assert "audio_recording" in detail
        audio_detail = detail["audio_recording"]
        assert audio_detail["s3_uri"] == "s3://bucket/recording.wav"
        assert audio_detail["duration_seconds"] == 42.5

    def test_nested_dataclass_with_none_values(self):
        """Test nested dataclasses skip None values during serialization."""
        audio_ref = AudioRecordingReference(
            s3_uri="s3://bucket/recording.wav",
            duration_seconds=None,
        )

        event = ConversationEvaluationRequested(
            conversation_id=uuid4(),
            call_id="call-123",
            user_id=uuid4(),
            account_id=uuid4(),
            account_name="test-account",
            project_id=uuid4(),
            channel="voice",
            is_test=False,
            call_metadata={},
            audio_recording=audio_ref,
        )

        detail = event.to_detail()

        audio_detail = detail["audio_recording"]
        # None values are skipped during serialization
        assert "duration_seconds" not in audio_detail
        assert "s3_uri" in audio_detail

    def test_list_serialization(self):
        """Test that lists are properly serialized."""
        event = ConversationEvaluationRequested(
            conversation_id=uuid4(),
            call_id="call-123",
            user_id=uuid4(),
            account_id=uuid4(),
            account_name="test-account",
            project_id=uuid4(),
            channel="voice",
            is_test=False,
            call_metadata={},
            transcript=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
            tool_calls=[{"tool": "search", "args": {"query": "menu"}}],
            turn_latencies_ms=[123.4, 234.5, 345.6],
        )

        detail = event.to_detail()

        assert detail["transcript"] == [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        assert detail["tool_calls"] == [{"tool": "search", "args": {"query": "menu"}}]
        assert detail["turn_latencies_ms"] == [123.4, 234.5, 345.6]

    def test_empty_lists_included(self):
        """Test that empty lists are included in serialization."""
        event = ConversationEvaluationRequested(
            conversation_id=uuid4(),
            call_id="call-123",
            user_id=uuid4(),
            account_id=uuid4(),
            account_name="test-account",
            project_id=uuid4(),
            channel="voice",
            is_test=False,
            call_metadata={},
            transcript=[],  # Empty list
            tool_calls=[],  # Empty list
            turn_latencies_ms=[],  # Empty list
        )

        detail = event.to_detail()

        # Empty lists should be included
        assert "transcript" in detail
        assert detail["transcript"] == []
        assert "tool_calls" in detail
        assert detail["tool_calls"] == []
        assert "turn_latencies_ms" in detail
        assert detail["turn_latencies_ms"] == []


class TestNestedDataclassListSerialization:
    """Test serialization of lists containing dataclasses."""

    @dataclass
    class NestedItem:
        """Test dataclass for nested list items."""

        id: UUID
        name: str
        timestamp: datetime

    @dataclass
    class EventWithNestedList(BaseEvent):
        """Test event with a list of dataclasses."""

        detail_type = "test.NestedList"
        items: list["TestNestedDataclassListSerialization.NestedItem"]

    def test_list_of_dataclasses_serialization(self):
        """Test that lists containing dataclasses are recursively serialized."""
        item1_id = uuid4()
        item2_id = uuid4()

        item1 = self.NestedItem(
            id=item1_id,
            name="Item 1",
            timestamp=datetime(2024, 3, 12, 10, 0, 0),
        )
        item2 = self.NestedItem(
            id=item2_id,
            name="Item 2",
            timestamp=datetime(2024, 3, 12, 11, 0, 0),
        )

        event = self.EventWithNestedList(items=[item1, item2])
        detail = event.to_detail()

        assert "items" in detail
        assert len(detail["items"]) == 2

        # Check first item - UUIDs and datetimes are properly serialized
        assert detail["items"][0]["id"] == str(item1_id)  # UUID serialized to string
        assert detail["items"][0]["name"] == "Item 1"
        assert (
            detail["items"][0]["timestamp"] == "2024-03-12T10:00:00"
        )  # datetime serialized

        # Check second item
        assert detail["items"][1]["id"] == str(item2_id)  # UUID serialized to string
        assert detail["items"][1]["name"] == "Item 2"
        assert (
            detail["items"][1]["timestamp"] == "2024-03-12T11:00:00"
        )  # datetime serialized


class TestComplexNesting:
    """Test deeply nested dataclass serialization scenarios."""

    @dataclass
    class Level3:
        """Deeply nested dataclass."""

        value: str
        timestamp: datetime

    @dataclass
    class Level2:
        """Mid-level nested dataclass."""

        id: UUID
        nested: "TestComplexNesting.Level3"

    @dataclass
    class ComplexEvent(BaseEvent):
        """Event with deep nesting."""

        detail_type = "test.Complex"
        level2: "TestComplexNesting.Level2"
        level2_list: list["TestComplexNesting.Level2"]

    def test_deep_nesting_serialization(self):
        """Test serialization of deeply nested dataclasses."""
        level2_id = uuid4()
        timestamp = datetime(2024, 3, 12, 12, 0, 0)

        level3 = self.Level3(value="deep", timestamp=timestamp)
        level2 = self.Level2(id=level2_id, nested=level3)

        event = self.ComplexEvent(level2=level2, level2_list=[level2])
        detail = event.to_detail()

        # Check single nested object - proper recursive serialization
        assert detail["level2"]["id"] == str(level2_id)  # UUID serialized to string
        assert detail["level2"]["nested"]["value"] == "deep"
        assert (
            detail["level2"]["nested"]["timestamp"] == "2024-03-12T12:00:00"
        )  # datetime serialized

        # Check list of nested objects
        assert len(detail["level2_list"]) == 1
        assert detail["level2_list"][0]["id"] == str(level2_id)  # UUID serialized
        assert detail["level2_list"][0]["nested"]["value"] == "deep"
        assert (
            detail["level2_list"][0]["nested"]["timestamp"] == "2024-03-12T12:00:00"
        )  # datetime serialized


class TestSerializeDataclassDirectly:
    """Test _serialize_dataclass static method directly for coverage.

    This tests the internal serialization helper that handles edge cases
    not reached through the normal to_detail() flow due to asdict() behavior.
    """

    @dataclass
    class NestedWithAll:
        """Dataclass with all supported types."""

        id: UUID
        name: str
        timestamp: datetime
        count: int
        optional: str | None

    @dataclass
    class Container:
        """Dataclass containing nested dataclasses."""

        nested: "TestSerializeDataclassDirectly.NestedWithAll"
        nested_list: list["TestSerializeDataclassDirectly.NestedWithAll"]

    def test_serialize_dataclass_with_uuid_datetime(self):
        """Test _serialize_dataclass handles UUID and datetime serialization."""
        test_id = uuid4()
        test_time = datetime(2024, 3, 12, 15, 30, 0)

        obj = self.NestedWithAll(
            id=test_id,
            name="test",
            timestamp=test_time,
            count=42,
            optional=None,
        )

        result = BaseEvent._serialize_dataclass(obj)

        assert result["id"] == str(test_id)  # UUID serialized to string
        assert result["name"] == "test"
        assert result["timestamp"] == "2024-03-12T15:30:00"  # datetime serialized
        assert result["count"] == 42
        assert "optional" not in result  # None values skipped

    def test_serialize_dataclass_with_nested_dataclass(self):
        """Test _serialize_dataclass recursively handles nested dataclasses."""
        inner_id = uuid4()
        inner_time = datetime(2024, 3, 12, 16, 0, 0)

        inner = self.NestedWithAll(
            id=inner_id,
            name="inner",
            timestamp=inner_time,
            count=10,
            optional="value",
        )

        outer = self.Container(nested=inner, nested_list=[inner])

        result = BaseEvent._serialize_dataclass(outer)

        # Nested dataclasses are properly serialized with UUID and datetime conversion
        assert result["nested"]["id"] == str(inner_id)  # UUID converted to string
        assert (
            result["nested"]["timestamp"] == "2024-03-12T16:00:00"
        )  # datetime converted
        assert result["nested"]["optional"] == "value"

        # Check list of nested dataclasses
        assert len(result["nested_list"]) == 1
        assert result["nested_list"][0]["id"] == str(inner_id)
        assert result["nested_list"][0]["timestamp"] == "2024-03-12T16:00:00"

    def test_serialize_dataclass_with_none_in_nested(self):
        """Test _serialize_dataclass skips None in nested dataclasses."""
        obj = self.NestedWithAll(
            id=uuid4(),
            name="test",
            timestamp=datetime(2024, 3, 12, 17, 0, 0),
            count=5,
            optional=None,  # Should be skipped
        )

        result = BaseEvent._serialize_dataclass(obj)

        assert "optional" not in result
