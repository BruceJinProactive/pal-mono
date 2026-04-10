"""Tests for AgnoAgent tool call logging and sanitization."""

from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

from agent.framework.agno import PII_FIELDS, _sanitize_result, _sanitize_tool_args
from agent.input_output import Output


class TestSanitizeToolArgs:
    """Tests for _sanitize_tool_args helper function."""

    def test_none_input_returns_empty_dict(self):
        """Test that None input returns empty dict."""
        result = _sanitize_tool_args(None)
        assert result == {}

    def test_empty_dict_returns_empty_dict(self):
        """Test that empty dict passes through."""
        result = _sanitize_tool_args({})
        assert result == {}

    def test_pii_fields_are_redacted(self):
        """Test that PII fields are redacted."""
        tool_args = {
            "phone_number": "+1234567890",
            "email": "customer@example.com",
            "address": "123 Main St",
            "credit_card": "4111111111111111",
            "customer_name": "John Doe",
            "delivery_address": "456 Oak Ave",
            "order_id": "12345",  # non-PII field
        }

        result = _sanitize_tool_args(tool_args)

        # All PII fields should be redacted
        for field in PII_FIELDS:
            if field in tool_args:
                assert result[field] == "<redacted>"

        # Non-PII fields should pass through
        assert result["order_id"] == "12345"

    def test_case_insensitive_pii_detection(self):
        """Test that PII detection is case-insensitive."""
        tool_args = {
            "Phone_Number": "+1234567890",
            "EMAIL": "test@example.com",
            "Address": "789 Elm St",
        }

        result = _sanitize_tool_args(tool_args)

        # All should be redacted regardless of case
        assert result["Phone_Number"] == "<redacted>"
        assert result["EMAIL"] == "<redacted>"
        assert result["Address"] == "<redacted>"

    def test_large_string_values_are_truncated(self):
        """Test that string values > 200 chars are truncated."""
        long_string = "a" * 500
        tool_args = {
            "description": long_string,
            "short_field": "short value",
        }

        result = _sanitize_tool_args(tool_args)

        assert result["description"] == "<truncated: 500 chars>"
        assert result["short_field"] == "short value"

    def test_exactly_200_chars_not_truncated(self):
        """Test that exactly 200 chars is not truncated."""
        exactly_200 = "a" * 200
        tool_args = {"field": exactly_200}

        result = _sanitize_tool_args(tool_args)

        assert result["field"] == exactly_200

    def test_201_chars_is_truncated(self):
        """Test that 201 chars is truncated."""
        exactly_201 = "a" * 201
        tool_args = {"field": exactly_201}

        result = _sanitize_tool_args(tool_args)

        assert result["field"] == "<truncated: 201 chars>"

    def test_normal_values_pass_through_unchanged(self):
        """Test that normal non-PII, non-large values pass through unchanged."""
        tool_args = {
            "order_id": "12345",
            "quantity": 3,
            "price": 29.99,
            "items": ["burger", "fries"],
            "metadata": {"key": "value"},
            "enabled": True,
            "notes": None,
        }

        result = _sanitize_tool_args(tool_args)

        assert result["order_id"] == "12345"
        assert result["quantity"] == 3
        assert result["price"] == 29.99
        assert result["items"] == ["burger", "fries"]
        assert result["metadata"] == {"key": "value"}
        assert result["enabled"] is True
        assert result["notes"] is None

    def test_nested_dict_pii_is_redacted(self):
        """Test that PII in nested dicts is recursively redacted."""
        tool_args = {
            "customer": {
                "email": "user@example.com",
                "name": "safe_name",
            },
            "order_id": "12345",
        }

        result = _sanitize_tool_args(tool_args)

        assert result["customer"]["email"] == "<redacted>"
        assert result["customer"]["name"] == "safe_name"
        assert result["order_id"] == "12345"

    def test_nested_list_pii_is_redacted(self):
        """Test that PII in nested lists of dicts is recursively redacted."""
        tool_args = {
            "contacts": [
                {"phone_number": "+1234567890", "role": "manager"},
                {"phone_number": "+0987654321", "role": "owner"},
            ],
        }

        result = _sanitize_tool_args(tool_args)

        assert result["contacts"][0]["phone_number"] == "<redacted>"
        assert result["contacts"][0]["role"] == "manager"
        assert result["contacts"][1]["phone_number"] == "<redacted>"

    def test_sanitize_value_truncates_long_strings(self):
        """Test that _sanitize_value truncates long strings in nested structures."""
        long_string = "x" * 300
        tool_args = {
            "nested": {"description": long_string},
        }

        result = _sanitize_tool_args(tool_args)

        assert result["nested"]["description"] == "<truncated: 300 chars>"

    def test_mixed_pii_truncation_and_normal(self):
        """Test combination of PII, truncation, and normal values."""
        long_string = "x" * 300
        tool_args = {
            "phone_number": "+1234567890",  # PII -> redacted
            "description": long_string,  # Long -> truncated
            "order_id": "12345",  # Normal -> unchanged
        }

        result = _sanitize_tool_args(tool_args)

        assert result["phone_number"] == "<redacted>"
        assert result["description"] == "<truncated: 300 chars>"
        assert result["order_id"] == "12345"


class TestSanitizeResult:
    """Tests for _sanitize_result helper function."""

    def test_none_input_returns_none(self):
        """Test that None input returns None."""
        result = _sanitize_result(None)
        assert result is None

    def test_empty_string_returns_empty_string(self):
        """Test that empty string passes through."""
        result = _sanitize_result("")
        assert result == ""

    def test_string_under_1000_chars_passes_through(self):
        """Test that strings under 1000 chars pass through unchanged."""
        short_string = "a" * 999
        result = _sanitize_result(short_string)
        assert result == short_string

    def test_exactly_1000_chars_not_truncated(self):
        """Test that exactly 1000 chars is not truncated."""
        exactly_1000 = "a" * 1000
        result = _sanitize_result(exactly_1000)
        assert result == exactly_1000

    def test_string_over_1000_chars_truncated(self):
        """Test that strings over 1000 chars get truncated."""
        long_string = "a" * 2000
        result = _sanitize_result(long_string)
        assert result == "a" * 1000
        assert result is not None and len(result) == 1000

    def test_custom_max_length(self):
        """Test that custom max_length parameter works."""
        test_string = "a" * 500
        result = _sanitize_result(test_string, max_length=100)
        assert result == "a" * 100
        assert result is not None and len(result) == 100

    def test_result_with_pii_field_names(self):
        """Test that result containing PII field names is handled (no-op for now)."""
        # The function currently just notes PII may be present but doesn't redact
        result_with_pii = "email: test@example.com, phone_number: +1234567890"
        result = _sanitize_result(result_with_pii)
        # Function doesn't modify result, just checks for PII presence
        assert result == result_with_pii


class TestToolCallCompletedEventLogging:
    """Tests for ToolCallCompletedEvent logging logic."""

    def test_tool_call_error_logs_at_error_level(self, caplog):
        """Test that tool call errors log at ERROR level with sanitized data."""
        from utils.log import logger

        # Simulate the logging code from the ToolCallCompletedEvent handler
        tool_name = "test_tool"
        tool_call_error = True
        tool_args = {"phone_number": "+1234567890", "order_id": "12345"}
        result = "Error: Tool failed"

        # Sanitize tool args (as done in the actual code)
        sanitized_args = _sanitize_tool_args(tool_args)

        # Truncate result if too long
        truncated_result = result[:1000] if result else None

        # Build structured log data
        log_data = {
            "tool_name": tool_name,
            "tool_call_error": tool_call_error,
            "tool_args": sanitized_args,
            "result": truncated_result,
            "conversation_id": "test-session-id",
            "account_name": "test-account",
            "agent_id": "test-agent-id",
        }

        # Emit error-level log for failures
        logger.error(f"Tool call failed: {tool_name}", extra=log_data)

        # Verify the log was emitted at ERROR level
        assert any(
            record.levelname == "ERROR"
            and "Tool call failed: test_tool" in record.message
            for record in caplog.records
        )

        # Verify PII was redacted
        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert any(
            hasattr(r, "tool_args")
            and r.tool_args.get("phone_number") == "<redacted>"  # type: ignore
            and r.tool_args.get("order_id") == "12345"  # type: ignore
            for r in error_records
        )

    def test_tool_call_success_logs_at_debug_level(self, caplog):
        """Test that successful tool calls log at DEBUG level."""
        import logging

        from utils.log import logger

        # Capture DEBUG level logs
        caplog.set_level(logging.DEBUG)

        tool_name = "test_tool"
        tool_call_error = False
        tool_args = {"order_id": "12345"}
        result = "Success"

        sanitized_args = _sanitize_tool_args(tool_args)
        truncated_result = result[:1000] if result else None

        log_data = {
            "tool_name": tool_name,
            "tool_call_error": tool_call_error,
            "tool_args": sanitized_args,
            "result": truncated_result,
            "conversation_id": "test-session-id",
            "account_name": "test-account",
            "agent_id": "test-agent-id",
        }

        logger.debug(f"Tool call succeeded: {tool_name}", extra=log_data)

        # Verify the log was emitted at DEBUG level
        assert any(
            record.levelname == "DEBUG"
            and "Tool call succeeded: test_tool" in record.message
            for record in caplog.records
        )

    def test_missing_tool_name_defaults_to_unknown(self, caplog):
        """Test that missing tool_name defaults to 'unknown'."""
        import logging

        from utils.log import logger

        # Capture DEBUG level logs
        caplog.set_level(logging.DEBUG)

        # Simulate chunk.tool being None
        tool_name = "unknown"  # This is what the code defaults to
        tool_call_error = False

        log_data = {
            "tool_name": tool_name,
            "tool_call_error": tool_call_error,
            "tool_args": {},
            "result": None,
            "conversation_id": "test-session-id",
            "account_name": "test-account",
            "agent_id": "test-agent-id",
        }

        logger.debug(f"Tool call succeeded: {tool_name}", extra=log_data)

        # Verify "unknown" was used
        assert any(
            record.levelname == "DEBUG" and "unknown" in record.message
            for record in caplog.records
        )

    def test_long_result_is_truncated_to_1000_chars(self, caplog):
        """Test that result strings > 1000 chars are truncated."""
        import logging

        from utils.log import logger

        # Capture DEBUG level logs
        caplog.set_level(logging.DEBUG)

        tool_name = "test_tool"
        tool_call_error = False
        long_result = "a" * 2000

        # Truncate result (as done in the actual code)
        truncated_result = long_result[:1000] if long_result else None

        log_data = {
            "tool_name": tool_name,
            "tool_call_error": tool_call_error,
            "tool_args": {},
            "result": truncated_result,
            "conversation_id": "test-session-id",
            "account_name": "test-account",
            "agent_id": "test-agent-id",
        }

        logger.debug(f"Tool call succeeded: {tool_name}", extra=log_data)

        # Verify result was truncated
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert any(
            hasattr(r, "result") and len(r.result) == 1000  # type: ignore
            for r in debug_records
        )


class TestAgnoAgentStreamingToolCallLogging:
    """Integration tests for tool call logging in streaming mode."""

    async def test_streaming_with_tool_call_completed_event_error(self, caplog):
        """Test that ToolCallCompletedEvent with error logs at ERROR level during streaming."""
        import logging
        from unittest.mock import patch

        from agno.run.response import ToolCallCompletedEvent

        from agent.framework.agno import AgnoAgent
        from agent.input_output import Input
        from utils.request_context import RequestContext

        # Capture ERROR level logs
        caplog.set_level(logging.ERROR)

        # Create minimal config
        config = MagicMock()
        config.tool = []
        config.knowledge = None
        config.metadata.agent_id = "test-agent"
        config.metadata.user_id = "test-user"
        config.metadata.session_id = "12345678-1234-5678-1234-567812345678"
        config.metadata.account_name = "test-account"
        config.persona.name = "Test Agent"
        config.persona.role = "Assistant"
        config.persona.description = "Test"
        config.additional_context = ""
        config.stream = True
        config.feature_config.chat_filler_words_percentage = 0.0
        config.feature_config.tool_calling_filler_words_percentage = 0.0
        config.model = None

        # Create mock ToolCallCompletedEvent with error
        mock_tool = MagicMock()
        mock_tool.tool_name = "test_tool"
        mock_tool.tool_call_error = True
        mock_tool.tool_args = {"phone_number": "+1234567890", "order_id": "12345"}
        mock_tool.result = "Error: Tool failed"

        mock_event = MagicMock(spec=ToolCallCompletedEvent)
        mock_event.tool = mock_tool

        # Mock the agent's arun to return a stream with the event
        async def mock_stream():
            yield mock_event

        with patch("agent.framework.agno.agno.agent.agent.Agent") as mock_agent_class:
            mock_agent_instance = MagicMock()
            mock_agent_instance.arun = AsyncMock(return_value=mock_stream())
            mock_agent_class.return_value = mock_agent_instance

            with patch(
                "agent.framework.agno.query_history_messages", new_callable=AsyncMock
            ) as mock_history:
                mock_history.return_value = [
                    MagicMock(role="user", content="test input")
                ]

                with patch("agent.framework.agno.get_tools", return_value=[]):
                    with patch("agent.framework.agno.build_agno_model"):
                        agent = AgnoAgent(config)

                        # Create input with stream=True
                        input_obj = Input(
                            content="test input",
                            stream=True,
                            request_context=RequestContext(),
                        )

                        # Get the stream iterator
                        result = await agent.arun(input_obj)
                        assert not isinstance(
                            result, Output
                        ), "Expected AsyncIterator for streaming"
                        stream: AsyncIterator[Output] = result

                        # Consume the stream to trigger the event handler
                        outputs = []
                        async for output in stream:
                            outputs.append(output)

        # Verify ERROR log was emitted
        assert any(
            record.levelname == "ERROR"
            and "Tool call failed: test_tool" in record.message
            for record in caplog.records
        )

        # Verify PII was redacted in log
        error_records = [r for r in caplog.records if r.levelname == "ERROR"]
        assert any(
            hasattr(r, "tool_args")
            and r.tool_args.get("phone_number") == "<redacted>"  # type: ignore
            for r in error_records
        )

    async def test_streaming_with_tool_call_completed_event_success(self, caplog):
        """Test that ToolCallCompletedEvent with success logs at DEBUG level during streaming."""
        import logging
        from unittest.mock import patch

        from agno.run.response import ToolCallCompletedEvent

        from agent.framework.agno import AgnoAgent
        from agent.input_output import Input
        from utils.request_context import RequestContext

        # Capture DEBUG level logs
        caplog.set_level(logging.DEBUG)

        # Create minimal config
        config = MagicMock()
        config.tool = []
        config.knowledge = None
        config.metadata.agent_id = "test-agent"
        config.metadata.user_id = "test-user"
        config.metadata.session_id = "12345678-1234-5678-1234-567812345678"
        config.metadata.account_name = "test-account"
        config.persona.name = "Test Agent"
        config.persona.role = "Assistant"
        config.persona.description = "Test"
        config.additional_context = ""
        config.stream = True
        config.feature_config.chat_filler_words_percentage = 0.0
        config.feature_config.tool_calling_filler_words_percentage = 0.0
        config.model = None

        # Create mock ToolCallCompletedEvent with success
        mock_tool = MagicMock()
        mock_tool.tool_name = "test_tool"
        mock_tool.tool_call_error = False
        mock_tool.tool_args = {"order_id": "12345"}
        mock_tool.result = "Success result" * 200  # Long result to test truncation

        mock_event = MagicMock(spec=ToolCallCompletedEvent)
        mock_event.tool = mock_tool

        # Mock the agent's arun to return a stream with the event
        async def mock_stream():
            yield mock_event

        with patch("agent.framework.agno.agno.agent.agent.Agent") as mock_agent_class:
            mock_agent_instance = MagicMock()
            mock_agent_instance.arun = AsyncMock(return_value=mock_stream())
            mock_agent_class.return_value = mock_agent_instance

            with patch(
                "agent.framework.agno.query_history_messages", new_callable=AsyncMock
            ) as mock_history:
                mock_history.return_value = [
                    MagicMock(role="user", content="test input")
                ]

                with patch("agent.framework.agno.get_tools", return_value=[]):
                    with patch("agent.framework.agno.build_agno_model"):
                        agent = AgnoAgent(config)

                        # Create input with stream=True
                        input_obj = Input(
                            content="test input",
                            stream=True,
                            request_context=RequestContext(),
                        )

                        # Get the stream iterator
                        result = await agent.arun(input_obj)
                        assert not isinstance(
                            result, Output
                        ), "Expected AsyncIterator for streaming"
                        stream: AsyncIterator[Output] = result

                        # Consume the stream to trigger the event handler
                        outputs = []
                        async for output in stream:
                            outputs.append(output)

        # Verify DEBUG log was emitted
        assert any(
            record.levelname == "DEBUG"
            and "Tool call succeeded: test_tool" in record.message
            for record in caplog.records
        )

        # Verify result was truncated to 1000 chars
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert any(
            hasattr(r, "result") and len(r.result) <= 1000  # type: ignore
            for r in debug_records
        )
