"""Tests for voice endpoint fire-and-forget task GC prevention.

Verifies that asyncio.create_task() calls store references in a module-level
set to prevent garbage collection before task completion.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestVoiceFireAndForgetTaskLeak:
    """Verify _voice.py stores task references to prevent GC."""

    def test_background_tasks_set_exists(self) -> None:
        """Module must have a set to store background task references."""
        import api.routes.internal._voice as voice_module

        assert hasattr(voice_module, "_background_tasks"), (
            "_voice.py must define `_background_tasks: set[asyncio.Task]` "
            "to prevent fire-and-forget tasks from being garbage collected"
        )
        assert isinstance(voice_module._background_tasks, set)

    def test_no_local_task_variable(self) -> None:
        """Task references must not be stored in local variables that go out of scope."""
        import inspect

        import api.routes.internal._voice as voice_module

        source = inspect.getsource(voice_module)
        lines = source.split("\n")

        for i, line in enumerate(lines):
            stripped = line.strip()
            if "_task = asyncio.create_task(" in stripped:
                pytest.fail(
                    f"Line {i+1}: task stored in local `_task` variable "
                    "that goes out of scope. Use module-level "
                    "_background_tasks set instead."
                )

    @pytest.mark.asyncio
    async def test_background_task_tracked_and_cleaned_up(self) -> None:
        """Task added to _background_tasks set and removed on completion."""
        from api.routes.internal._voice import _background_tasks

        completed = False

        async def dummy() -> None:
            nonlocal completed
            completed = True

        initial_count = len(_background_tasks)
        task = asyncio.create_task(dummy())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        await asyncio.wait_for(task, timeout=1)
        assert completed
        assert len(_background_tasks) == initial_count

    @pytest.mark.asyncio
    async def test_on_done_callback_logs_exception(self) -> None:
        """_on_done callback logs when task raises."""
        from api.routes.internal._voice import _background_tasks

        conversation_id = "test-conv-123"

        async def failing() -> None:
            raise RuntimeError("voice task error")

        initial_count = len(_background_tasks)
        task = asyncio.create_task(failing())
        _background_tasks.add(task)

        with patch("api.routes.internal._voice.logger") as mock_logger:

            def _on_done(t: asyncio.Task[object]) -> None:
                _background_tasks.discard(t)
                if not t.cancelled() and t.exception() is not None:
                    mock_logger.error(
                        "[Voice] Background evaluation task failed for conversation %s: %s",
                        conversation_id,
                        t.exception(),
                        exc_info=t.exception(),
                    )

            task.add_done_callback(_on_done)

            with pytest.raises(RuntimeError):
                await asyncio.wait_for(task, timeout=1)

            assert len(_background_tasks) == initial_count
            mock_logger.error.assert_called_once()
            assert "Voice" in str(mock_logger.error.call_args)

    @pytest.mark.asyncio
    async def test_end_voice_call_creates_tracked_task(self) -> None:
        """end_voice_call creates a tracked background task for evaluation."""
        from api.routes.internal._voice import _background_tasks, end_voice_call

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )

        conversation_id = uuid.uuid4()
        mock_conversation = MagicMock()
        mock_conversation.id = conversation_id
        mock_conversation.project_id = uuid.uuid4()
        mock_conversation.user_id = uuid.uuid4()
        mock_conversation.channel = MagicMock(value="voice")
        mock_conversation.is_test = False
        mock_conversation.customer_converted = None

        mock_request = MagicMock()
        mock_request.call_id = "call-123"
        mock_request.caller_number = "+15551234567"
        mock_request.dialed_number = "+15559876543"
        mock_request.duration_seconds = 30.0
        mock_request.close_reason = "agent_hangup"
        mock_request.conversation = []

        initial_count = len(_background_tasks)

        with (
            patch("api.routes.internal._voice.db") as mock_db,
            patch(
                "api.routes.internal._voice._get_default_analytics"
            ) as mock_default_analytics,
            patch(
                "api.routes.internal._voice._should_track_call_usage",
                return_value=(False, "test call"),
            ),
            patch(
                "api.routes.internal._voice._publish_livekit_evaluation_event",
                new_callable=AsyncMock,
            ),
            patch(
                "db.repositories.phone_call_repository.PhoneCallRepositoryAsync"
            ) as mock_phone_repo_cls,
        ):
            mock_conv_repo = AsyncMock()
            mock_conv_repo.get_conversation_by_call_id = AsyncMock(
                return_value=mock_conversation
            )
            mock_db.ConversationRepositoryAsync.return_value = mock_conv_repo

            mock_phone_repo = AsyncMock()
            mock_phone_repo.update_phone_call = AsyncMock(return_value=None)
            mock_phone_repo_cls.return_value = mock_phone_repo

            mock_default_analytics.return_value = {
                "ended_reason": MagicMock(value="agent_hangup"),
                "call_purpose": [MagicMock(value="general_inquiry")],
                "user_satisfaction": MagicMock(value="neutral"),
                "language": MagicMock(value="en"),
            }

            result = await end_voice_call(mock_request, mock_session)

            assert result["status"] == "success"
            assert str(conversation_id) in result["conversation_id"]
            # Task was tracked
            assert len(_background_tasks) >= initial_count

            # Wait for tasks to complete
            pending = [t for t in _background_tasks if not t.done()]
            if pending:
                await asyncio.wait(pending, timeout=2)

        await asyncio.sleep(0.01)
        assert len(_background_tasks) == initial_count
