"""Tests for process trace data model and builder."""

from services.eval_service._evaluators import ConversationRecord
from services.eval_service.process_trace import (
    ActionType,
    AudioContent,
    EventType,
    ProcessTrace,
    TextContent,
    TraceEvent,
    build_process_trace,
    get_text,
)
from services.eval_service.schema import EvalScenario


def _make_scenario(**overrides: object) -> EvalScenario:
    defaults = {
        "scenario_id": "test-scenario",
        "scenario": "Test",
        "test_category": "general",
        "user_turns": ["Hello"],
    }
    defaults.update(overrides)
    return EvalScenario(**defaults)


class TestGetText:
    def test_text_content(self) -> None:
        assert get_text(TextContent(text="hello")) == "hello"

    def test_audio_content_with_transcript(self) -> None:
        content = AudioContent(uri="s3://bucket/file.ogg", transcript="hello")
        assert get_text(content) == "hello"

    def test_audio_content_without_transcript(self) -> None:
        content = AudioContent(uri="s3://bucket/file.ogg")
        assert get_text(content) is None

    def test_none_content(self) -> None:
        assert get_text(None) is None


class TestProcessTrace:
    def test_get_events_filters_by_type(self) -> None:
        trace = ProcessTrace(
            scenario_id="test",
            driver_mode="http",
            events=[
                TraceEvent(event_type=EventType.USER_MESSAGE, turn_index=0),
                TraceEvent(event_type=EventType.AGENT_MESSAGE, turn_index=0),
                TraceEvent(event_type=EventType.USER_MESSAGE, turn_index=1),
            ],
        )
        user_events = trace.get_events(EventType.USER_MESSAGE)
        assert len(user_events) == 2
        agent_events = trace.get_events(EventType.AGENT_MESSAGE)
        assert len(agent_events) == 1

    def test_get_actions_returns_all_actions(self) -> None:
        from services.eval_service.process_trace import AgentAction

        action1 = AgentAction(
            action_type=ActionType.TOOL_CALL,
            arguments={"tool_name": "tool_a"},
        )
        action2 = AgentAction(
            action_type=ActionType.TOOL_CALL,
            arguments={"tool_name": "tool_b"},
        )
        trace = ProcessTrace(
            scenario_id="test",
            driver_mode="http",
            events=[
                TraceEvent(
                    event_type=EventType.ACTION,
                    turn_index=0,
                    actions=[action1],
                ),
                TraceEvent(
                    event_type=EventType.ACTION,
                    turn_index=1,
                    actions=[action2],
                ),
            ],
        )
        actions = trace.get_actions()
        assert len(actions) == 2
        assert actions[0] == (0, action1)
        assert actions[1] == (1, action2)

    def test_get_chat_history(self) -> None:
        trace = ProcessTrace(
            scenario_id="test",
            driver_mode="http",
            events=[
                TraceEvent(
                    event_type=EventType.USER_MESSAGE,
                    turn_index=0,
                    content=TextContent(text="Hi"),
                ),
                TraceEvent(
                    event_type=EventType.AGENT_MESSAGE,
                    turn_index=0,
                    content=TextContent(text="Hello!"),
                ),
            ],
        )
        history = trace.get_chat_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert isinstance(history[0]["content"], TextContent)
        assert history[1]["role"] == "agent"


class TestBuildProcessTraceHTTP:
    def test_basic_http_conversation(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "I want a pizza", "assistant": "What size?"},
                {"user": "Large please", "assistant": "Order placed!"},
            ],
        )

        trace = build_process_trace(record)

        assert trace.scenario_id == "test-scenario"
        assert trace.driver_mode == "http"
        assert len(trace.events) == 4  # 2 user + 2 agent messages
        user_events = trace.get_events(EventType.USER_MESSAGE)
        assert len(user_events) == 2
        assert get_text(user_events[0].content) == "I want a pizza"
        assert get_text(user_events[1].content) == "Large please"

    def test_http_with_tool_calls(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Order a pizza", "assistant": "Placing your order"},
            ],
            tool_calls=[
                {
                    "payload": {
                        "tool_name": "create_order",
                        "arguments": {"item": "pizza"},
                    }
                }
            ],
        )

        trace = build_process_trace(record)

        action_events = trace.get_events(EventType.ACTION)
        assert len(action_events) == 1
        actions = trace.get_actions()
        assert len(actions) == 1
        turn_idx, action = actions[0]
        assert action.action_type == ActionType.TOOL_CALL
        assert action.arguments["tool_name"] == "create_order"
        assert action.arguments["item"] == "pizza"

    def test_http_empty_turns(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(scenario=scenario, turns=[])

        trace = build_process_trace(record)

        assert trace.events == []

    def test_driver_mode_override(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(scenario=scenario, turns=[])

        trace = build_process_trace(record, driver_mode="direct")
        assert trace.driver_mode == "direct"


class TestBuildProcessTraceVoice:
    def test_basic_voice_conversation(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[],
            is_voice=True,
            voice_transcript=[
                {
                    "role": "user",
                    "content": "Hello",
                    "start_time": 0.0,
                    "end_time": 1.5,
                },
                {
                    "role": "assistant",
                    "content": "Hi there!",
                    "start_time": 2.0,
                    "end_time": 3.5,
                },
            ],
            audio_recording_s3_uri="s3://bucket/recording.ogg",
        )

        trace = build_process_trace(record)

        assert trace.driver_mode == "voice"
        assert len(trace.events) == 2

        user_event = trace.get_events(EventType.USER_MESSAGE)[0]
        assert isinstance(user_event.content, AudioContent)
        assert user_event.content.transcript == "Hello"
        assert user_event.content.uri == "s3://bucket/recording.ogg"
        assert user_event.content.duration_ms == 1500.0
        assert user_event.timestamp_ms == 0.0

    def test_voice_with_tool_calls(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[],
            is_voice=True,
            voice_transcript=[
                {
                    "role": "user",
                    "content": "Order pizza",
                    "start_time": 0.0,
                    "end_time": 1.0,
                },
                {
                    "role": "assistant",
                    "content": "Done!",
                    "start_time": 2.0,
                    "end_time": 3.0,
                },
            ],
            audio_recording_s3_uri="s3://bucket/call.ogg",
            tool_calls=[{"tool_name": "create_order", "arguments": {"item": "pizza"}}],
        )

        trace = build_process_trace(record)

        actions = trace.get_actions()
        assert len(actions) == 1
        _, action = actions[0]
        assert action.arguments["tool_name"] == "create_order"

    def test_voice_no_transcript_falls_back_to_http(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": "Hello"}],
            is_voice=True,
            voice_transcript=[],
        )

        trace = build_process_trace(record)

        # Falls back to HTTP-style when voice_transcript is empty
        user_events = trace.get_events(EventType.USER_MESSAGE)
        assert len(user_events) == 1
        assert isinstance(user_events[0].content, TextContent)

    def test_voice_unknown_role_skipped_without_advancing_turn(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[],
            is_voice=True,
            voice_transcript=[
                {"role": "user", "content": "Hi", "start_time": 0.0, "end_time": 1.0},
                {
                    "role": "system",
                    "content": "ignored",
                    "start_time": 1.5,
                    "end_time": 2.0,
                },
                {
                    "role": "assistant",
                    "content": "Hello",
                    "start_time": 2.5,
                    "end_time": 3.0,
                },
            ],
            audio_recording_s3_uri="s3://bucket/call.ogg",
        )

        trace = build_process_trace(record)

        # System role should be skipped; user and assistant share turn 0
        assert len(trace.events) == 2
        assert trace.events[0].turn_index == 0
        assert trace.events[1].turn_index == 0


class TestExtractToolResult:
    def test_scalar_result_wrapped_in_dict(self) -> None:
        from services.eval_service.process_trace import _extract_tool_result

        tc = {"result": "order-123"}
        result = _extract_tool_result(tc)
        assert result == {"value": "order-123"}

    def test_dict_result_returned_as_is(self) -> None:
        from services.eval_service.process_trace import _extract_tool_result

        tc = {"result": {"order_id": "123"}}
        result = _extract_tool_result(tc)
        assert result == {"order_id": "123"}

    def test_none_result(self) -> None:
        from services.eval_service.process_trace import _extract_tool_result

        tc = {"tool_name": "foo"}
        result = _extract_tool_result(tc)
        assert result is None


class TestToolTurnAssignment:
    def test_no_agent_events_assigns_turn_0(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[{"user": "Hi", "assistant": ""}],
            tool_calls=[{"tool_name": "foo", "arguments": {}}],
        )

        trace = build_process_trace(record)

        actions = trace.get_actions()
        assert len(actions) == 1
        turn_idx, _ = actions[0]
        # No agent messages means fallback to turn 0
        assert turn_idx == 0

    def test_msg_index_maps_to_correct_agent_turn(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hi", "assistant": "Hello"},
                {"user": "Order pizza", "assistant": "Done!"},
            ],
            tool_calls=[
                {"tool_name": "lookup", "arguments": {}, "_msg_index": 0},
                {"tool_name": "create_order", "arguments": {}, "_msg_index": 1},
            ],
        )

        trace = build_process_trace(record)

        actions = trace.get_actions()
        assert len(actions) == 2
        # First tool call maps to agent turn 0
        assert actions[0][0] == 0
        # Second tool call maps to agent turn 1
        assert actions[1][0] == 1

    def test_multiple_tool_calls_same_msg_index(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hi", "assistant": "Hello"},
                {"user": "Complex order", "assistant": "Processing"},
            ],
            tool_calls=[
                {"tool_name": "lookup", "arguments": {}, "_msg_index": 1},
                {"tool_name": "create_order", "arguments": {}, "_msg_index": 1},
            ],
        )

        trace = build_process_trace(record)

        actions = trace.get_actions()
        assert len(actions) == 2
        # Both tool calls should map to the same agent turn
        assert actions[0][0] == actions[1][0]

    def test_no_msg_index_falls_back_to_last_agent_turn(self) -> None:
        scenario = _make_scenario()
        record = ConversationRecord(
            scenario=scenario,
            turns=[
                {"user": "Hi", "assistant": "Hello"},
                {"user": "Order", "assistant": "Done"},
            ],
            tool_calls=[
                {"tool_name": "create_order", "arguments": {}},
            ],
        )

        trace = build_process_trace(record)

        actions = trace.get_actions()
        assert len(actions) == 1
        # No _msg_index → falls back to last agent turn (turn 1)
        assert actions[0][0] == 1
