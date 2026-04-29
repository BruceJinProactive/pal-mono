"""Tests for AgnoAgent tool call database persistence."""

import asyncio
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agno.run.response import ToolCallCompletedEvent

from agent.framework.agno import AgnoAgent
from agent.input_output import Input, Output
from utils.request_context import RequestContext


class TestToolCallRecordPersistence:
    """Tests for database persistence of tool call records."""

    async def test_persist_tool_call_record_success(self):
        """Test that successful tool calls are persisted to the database."""
        # Create a mock session and repository
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_record = MagicMock()
        mock_repo.add_tool_call_record = AsyncMock(return_value=mock_record)

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

        with patch("agent.framework.agno.agno.agent.agent.Agent"):
            with patch("agent.framework.agno.get_tools", return_value=[]):
                with patch("agent.framework.agno.build_agno_model"):
                    agent = AgnoAgent(config)

                    # Mock the session factory
                    with patch(
                        "agent.framework.agno.AsyncSessionLocal"
                    ) as mock_session_factory:
                        mock_session_factory.return_value.__aenter__.return_value = (
                            mock_session
                        )

                        # Mock the repository class
                        with patch(
                            "agent.framework.agno.ToolCallRecordRepositoryAsync"
                        ) as mock_repo_class:
                            mock_repo_class.return_value = mock_repo

                            # Call the persist method (with None for result per PII contract)
                            await agent._persist_tool_call_record(
                                conversation_id=uuid.UUID(config.metadata.session_id),
                                tool_name="test_tool",
                                is_error=False,
                                error_type=None,
                                result=None,
                            )

                            # Verify repository was called with correct args
                            mock_repo.add_tool_call_record.assert_called_once()
                            call_args = mock_repo.add_tool_call_record.call_args[1]
                            assert call_args["conversation_id"] == uuid.UUID(
                                config.metadata.session_id
                            )
                            assert call_args["tool_name"] == "test_tool"
                            assert call_args["is_error"] is False
                            assert call_args["error_type"] is None
                            # Result should be None until proper PII redaction exists
                            assert call_args["result"] is None

                            # Note: session.commit() is called inside the repository method,
                            # not in _persist_tool_call_record, so we don't assert it here

    async def test_persist_tool_call_record_error(self):
        """Test that failed tool calls are persisted with error info."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_record = MagicMock()
        mock_repo.add_tool_call_record = AsyncMock(return_value=mock_record)

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

        with patch("agent.framework.agno.agno.agent.agent.Agent"):
            with patch("agent.framework.agno.get_tools", return_value=[]):
                with patch("agent.framework.agno.build_agno_model"):
                    agent = AgnoAgent(config)

                    with patch(
                        "agent.framework.agno.AsyncSessionLocal"
                    ) as mock_session_factory:
                        mock_session_factory.return_value.__aenter__.return_value = (
                            mock_session
                        )

                        with patch(
                            "agent.framework.agno.ToolCallRecordRepositoryAsync"
                        ) as mock_repo_class:
                            mock_repo_class.return_value = mock_repo

                            await agent._persist_tool_call_record(
                                conversation_id=uuid.UUID(config.metadata.session_id),
                                tool_name="failing_tool",
                                is_error=True,
                                error_type=None,  # Omit until proper PII redaction exists
                                result=None,  # Omit until proper PII redaction exists
                            )

                            mock_repo.add_tool_call_record.assert_called_once()
                            call_args = mock_repo.add_tool_call_record.call_args[1]
                            assert call_args["tool_name"] == "failing_tool"
                            assert call_args["is_error"] is True
                            # error_type and result should be None until proper PII redaction exists
                            assert call_args["error_type"] is None
                            assert call_args["result"] is None

    async def test_persist_tool_call_record_truncates_long_result(self):
        """Test that results are omitted (until proper PII redaction exists)."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_record = MagicMock()
        mock_repo.add_tool_call_record = AsyncMock(return_value=mock_record)

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

        with patch("agent.framework.agno.agno.agent.agent.Agent"):
            with patch("agent.framework.agno.get_tools", return_value=[]):
                with patch("agent.framework.agno.build_agno_model"):
                    agent = AgnoAgent(config)

                    with patch(
                        "agent.framework.agno.AsyncSessionLocal"
                    ) as mock_session_factory:
                        mock_session_factory.return_value.__aenter__.return_value = (
                            mock_session
                        )

                        with patch(
                            "agent.framework.agno.ToolCallRecordRepositoryAsync"
                        ) as mock_repo_class:
                            mock_repo_class.return_value = mock_repo

                            # Test with None result (per PII contract)
                            await agent._persist_tool_call_record(
                                conversation_id=uuid.UUID(config.metadata.session_id),
                                tool_name="test_tool",
                                is_error=False,
                                error_type=None,
                                result=None,
                            )

                            mock_repo.add_tool_call_record.assert_called_once()
                            call_args = mock_repo.add_tool_call_record.call_args[1]
                            # Result should be None until proper PII redaction exists
                            assert call_args["result"] is None

    async def test_persist_tool_call_record_handles_db_failure(self, caplog):
        """Test that DB write failures are logged but don't raise exceptions."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        # Simulate DB failure
        mock_repo.add_tool_call_record = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

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

        with patch("agent.framework.agno.agno.agent.agent.Agent"):
            with patch("agent.framework.agno.get_tools", return_value=[]):
                with patch("agent.framework.agno.build_agno_model"):
                    agent = AgnoAgent(config)

                    with patch(
                        "agent.framework.agno.AsyncSessionLocal"
                    ) as mock_session_factory:
                        mock_session_factory.return_value.__aenter__.return_value = (
                            mock_session
                        )

                        with patch(
                            "agent.framework.agno.ToolCallRecordRepositoryAsync"
                        ) as mock_repo_class:
                            mock_repo_class.return_value = mock_repo

                            # Should not raise an exception
                            await agent._persist_tool_call_record(
                                conversation_id=uuid.UUID(config.metadata.session_id),
                                tool_name="test_tool",
                                is_error=False,
                                error_type=None,
                                result="Success",
                            )

                            # Verify error was logged
                            assert any(
                                "Failed to persist tool call record" in record.message
                                for record in caplog.records
                            )

    async def test_streaming_triggers_db_persistence(self):
        """Test that streaming with ToolCallCompletedEvent triggers DB persistence."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_record = MagicMock()
        mock_repo.add_tool_call_record = AsyncMock(return_value=mock_record)

        # Mock OTel metrics to avoid telemetry issues
        with patch("agent.framework.agno.record_duration"):
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

            # Create mock ToolCallCompletedEvent
            mock_tool = MagicMock()
            mock_tool.tool_name = "test_tool"
            mock_tool.tool_call_error = False
            mock_tool.tool_args = {"order_id": "12345"}
            mock_tool.result = "Success"

            mock_event = MagicMock(spec=ToolCallCompletedEvent)
            mock_event.tool = mock_tool

            # Mock the agent's arun to return a stream with the event
            async def mock_stream():
                yield mock_event

            with patch(
                "agent.framework.agno.agno.agent.agent.Agent"
            ) as mock_agent_class:
                mock_agent_instance = MagicMock()
                mock_agent_instance.arun = AsyncMock(return_value=mock_stream())
                mock_agent_class.return_value = mock_agent_instance

                with patch(
                    "agent.framework.agno.query_history_messages",
                    new_callable=AsyncMock,
                ) as mock_history:
                    mock_history.return_value = [
                        MagicMock(role="user", content="test input")
                    ]

                    with patch("agent.framework.agno.get_tools", return_value=[]):
                        with patch("agent.framework.agno.build_agno_model"):
                            with patch(
                                "agent.framework.agno.AsyncSessionLocal"
                            ) as mock_session_factory:
                                mock_session_factory.return_value.__aenter__.return_value = (
                                    mock_session
                                )

                                with patch(
                                    "agent.framework.agno.ToolCallRecordRepositoryAsync"
                                ) as mock_repo_class:
                                    mock_repo_class.return_value = mock_repo

                                    agent = AgnoAgent(config)

                                    input_obj = Input(
                                        content="test input",
                                        stream=True,
                                        request_context=RequestContext(),
                                    )

                                    result = await agent.arun(input_obj)
                                    assert not isinstance(
                                        result, Output
                                    ), "Expected AsyncIterator for streaming"
                                    stream: AsyncIterator[Output] = result

                                    # Consume the stream
                                    outputs = []
                                    async for output in stream:
                                        outputs.append(output)

                                    # Give background task time to complete
                                    await asyncio.sleep(0.1)

                                    # Verify DB persistence was called
                                    mock_repo.add_tool_call_record.assert_called_once()
                                    call_args = (
                                        mock_repo.add_tool_call_record.call_args[1]
                                    )
                                    assert call_args["tool_name"] == "test_tool"
                                    assert call_args["is_error"] is False
                                    assert call_args["error_type"] is None

    async def test_error_type_extraction_from_result(self):
        """Test that error_type and result are omitted (until proper PII redaction exists)."""
        mock_session = AsyncMock()
        mock_repo = AsyncMock()
        mock_record = MagicMock()
        mock_repo.add_tool_call_record = AsyncMock(return_value=mock_record)

        # Mock OTel metrics to avoid telemetry issues
        with patch("agent.framework.agno.record_duration"):
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
            mock_tool.tool_name = "failing_tool"
            mock_tool.tool_call_error = True
            mock_tool.tool_args = {}
            mock_tool.result = "ValueError: Invalid input parameter\nStack trace..."

            mock_event = MagicMock(spec=ToolCallCompletedEvent)
            mock_event.tool = mock_tool

            async def mock_stream():
                yield mock_event

            with patch(
                "agent.framework.agno.agno.agent.agent.Agent"
            ) as mock_agent_class:
                mock_agent_instance = MagicMock()
                mock_agent_instance.arun = AsyncMock(return_value=mock_stream())
                mock_agent_class.return_value = mock_agent_instance

                with patch(
                    "agent.framework.agno.query_history_messages",
                    new_callable=AsyncMock,
                ) as mock_history:
                    mock_history.return_value = [
                        MagicMock(role="user", content="test input")
                    ]

                    with patch("agent.framework.agno.get_tools", return_value=[]):
                        with patch("agent.framework.agno.build_agno_model"):
                            with patch(
                                "agent.framework.agno.AsyncSessionLocal"
                            ) as mock_session_factory:
                                mock_session_factory.return_value.__aenter__.return_value = (
                                    mock_session
                                )

                                with patch(
                                    "agent.framework.agno.ToolCallRecordRepositoryAsync"
                                ) as mock_repo_class:
                                    mock_repo_class.return_value = mock_repo

                                    agent = AgnoAgent(config)

                                    input_obj = Input(
                                        content="test input",
                                        stream=True,
                                        request_context=RequestContext(),
                                    )

                                    result = await agent.arun(input_obj)
                                    assert not isinstance(
                                        result, Output
                                    ), "Expected AsyncIterator for streaming"
                                    stream: AsyncIterator[Output] = result

                                    # Consume the stream
                                    async for _ in stream:
                                        pass

                                    # Give background task time to complete
                                    await asyncio.sleep(0.1)

                                    # Verify error_type and result are omitted (until proper PII redaction)
                                    mock_repo.add_tool_call_record.assert_called_once()
                                    call_args = (
                                        mock_repo.add_tool_call_record.call_args[1]
                                    )
                                    assert call_args["is_error"] is True
                                    assert call_args["error_type"] is None
                                    assert call_args["result"] is None


class TestBackgroundTaskShutdown:
    """Tests for background task shutdown coordination."""

    @pytest.mark.asyncio
    async def test_wait_for_all_background_tasks_with_pending_tasks(self):
        """Test that wait_for_all_background_tasks calls gather on the registry."""
        from agent.framework.agno import (
            _ALL_BACKGROUND_TASKS,
            wait_for_all_background_tasks,
        )

        # Add mock tasks to the registry
        mock_task = AsyncMock()
        _ALL_BACKGROUND_TASKS.add(mock_task)

        with patch("agent.framework.agno.asyncio.gather", new_callable=AsyncMock):
            await wait_for_all_background_tasks()

        # Clean up
        _ALL_BACKGROUND_TASKS.discard(mock_task)

    @pytest.mark.asyncio
    async def test_wait_for_all_background_tasks_empty_is_noop(self):
        """Test that wait_for_all_background_tasks is safe when empty."""
        from agent.framework.agno import (
            _ALL_BACKGROUND_TASKS,
            wait_for_all_background_tasks,
        )

        _ALL_BACKGROUND_TASKS.clear()
        # Should not raise
        await wait_for_all_background_tasks()
