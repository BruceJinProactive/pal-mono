"""Tests for chat fire-and-forget task GC prevention.

Verifies that asyncio.create_task() calls store references in a module-level
set to prevent garbage collection before task completion.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas.chat.chat import ChatResponse


class TestChatFireAndForgetTaskLeak:
    """Verify chat.py stores task references to prevent GC."""

    def test_background_tasks_set_exists(self) -> None:
        """Module must have a set to store background task references."""
        import api.routes.chat.chat as chat_module

        assert hasattr(chat_module, "_background_tasks"), (
            "chat.py must define `_background_tasks: set[asyncio.Task]` "
            "to prevent fire-and-forget tasks from being garbage collected"
        )
        assert isinstance(chat_module._background_tasks, set)

    def test_no_bare_create_task(self) -> None:
        """create_task calls must store the returned task reference."""
        import inspect

        import api.routes.chat.chat as chat_module

        source = inspect.getsource(chat_module)
        lines = source.split("\n")

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("asyncio.create_task(") and "=" not in line:
                pytest.fail(
                    f"Line {i+1}: bare `asyncio.create_task()` without "
                    "storing reference. Task can be GC'd before completion."
                )

    @pytest.mark.asyncio
    async def test_background_task_tracked_and_cleaned_up(self) -> None:
        """Task added to _background_tasks set and removed on completion."""
        from api.routes.chat.chat import _background_tasks

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
        from api.routes.chat.chat import _background_tasks

        async def failing() -> None:
            raise RuntimeError("chat task error")

        initial_count = len(_background_tasks)
        task = asyncio.create_task(failing())
        _background_tasks.add(task)

        with patch("api.routes.chat.chat.logger") as mock_logger:

            def _on_done(t: asyncio.Task[object]) -> None:
                _background_tasks.discard(t)
                if not t.cancelled() and t.exception() is not None:
                    mock_logger.error(
                        "[Chat] Background generate_and_send task failed: %s",
                        t.exception(),
                        exc_info=t.exception(),
                    )

            task.add_done_callback(_on_done)

            with pytest.raises(RuntimeError):
                await asyncio.wait_for(task, timeout=1)

            assert len(_background_tasks) == initial_count
            mock_logger.error.assert_called_once()
            assert "Chat" in str(mock_logger.error.call_args)

    @pytest.mark.asyncio
    async def test_relay_response_creates_tracked_task(self) -> None:
        """chat() with relay_response=True creates a tracked background task."""
        from api.routes.chat.chat import _background_tasks, chat

        mock_session = AsyncMock()
        mock_message = MagicMock()
        mock_message.metadata = None
        mock_message.channel = "api"

        mock_request = MagicMock()
        mock_request.stream = False
        mock_request.relay_response = True
        mock_request.message = mock_message

        initial_count = len(_background_tasks)

        with (
            patch(
                "api.routes.chat.chat.get_chat_response_async",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("api.routes.chat.chat.send_messages", return_value=None),
            patch("api.routes.chat.chat.RequestContext", return_value=MagicMock()),
            patch("api.routes.chat.chat.set_testing_mode"),
            patch("api.routes.chat.chat.trace") as mock_trace,
            patch("api.routes.chat.chat.AsyncSessionLocal") as mock_session_factory,
        ):
            mock_span = MagicMock()
            mock_span.is_recording.return_value = False
            mock_trace.get_current_span.return_value = mock_span
            mock_async_session = AsyncMock()
            mock_async_session.commit = AsyncMock()
            mock_session_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_async_session
            )
            mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            response = await chat(mock_request, mock_session)

            assert isinstance(response, ChatResponse)
            assert response.status == "success"
            # Task was tracked
            assert len(_background_tasks) >= initial_count

            # Wait for tasks to complete
            pending = [t for t in _background_tasks if not t.done()]
            if pending:
                await asyncio.wait(pending, timeout=2)

        # After completion, tasks are cleaned up
        await asyncio.sleep(0.01)
        assert len(_background_tasks) == initial_count
