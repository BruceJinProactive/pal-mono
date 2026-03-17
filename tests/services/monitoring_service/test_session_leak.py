"""Tests for monitoring service DB connection leak fixes.

Verifies that _rerun_monitoring_analysis_background:
- Uses `async with AsyncSessionLocal()` (not `async for ... break`)
- Properly calls __aenter__/__aexit__ on success and error paths
- Stores background task references to prevent GC
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_async_session() -> AsyncMock:
    """Mock async session that tracks context manager usage."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


class TestRerunBackgroundSessionLifecycle:
    """Verify _rerun_monitoring_analysis_background uses context manager for sessions."""

    @pytest.mark.asyncio
    async def test_session_uses_context_manager_on_success(
        self,
        mock_async_session: AsyncMock,
    ) -> None:
        """Session __aenter__ and __aexit__ must both be called on success path."""
        run_id = uuid.uuid4()
        config_id = uuid.uuid4()

        mock_llm_result = {"analysis_result": {"result": "pass", "details": "All good"}}

        with (
            patch("db.session.AsyncSessionLocal") as mock_factory,
            patch(
                "services.monitoring_service._llm.generate_monitoring_llm_prompt",
                new_callable=AsyncMock,
                return_value=mock_llm_result,
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync"
            ) as mock_repo_cls,
        ):
            mock_factory.return_value = mock_async_session
            mock_repo_cls.return_value = AsyncMock()

            from services.monitoring_service._implementation import (
                _rerun_monitoring_analysis_background,
            )

            await _rerun_monitoring_analysis_background(
                run_id=run_id,
                monitoring_config_id=config_id,
                media_url="s3://bucket/image.jpg",
                is_video=False,
            )

            mock_async_session.__aenter__.assert_awaited_once()
            mock_async_session.__aexit__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_uses_context_manager_on_error(
        self,
        mock_async_session: AsyncMock,
    ) -> None:
        """Session __aexit__ must be called even when LLM call raises."""
        run_id = uuid.uuid4()
        config_id = uuid.uuid4()

        with (
            patch("db.session.AsyncSessionLocal") as mock_factory,
            patch(
                "services.monitoring_service._llm.generate_monitoring_llm_prompt",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM timeout"),
            ),
            patch(
                "services.monitoring_service._implementation.MonitoringRunRepositoryAsync"
            ) as mock_repo_cls,
        ):
            mock_factory.return_value = mock_async_session
            mock_repo_cls.return_value = AsyncMock()

            from services.monitoring_service._implementation import (
                _rerun_monitoring_analysis_background,
            )

            await _rerun_monitoring_analysis_background(
                run_id=run_id,
                monitoring_config_id=config_id,
                media_url="s3://bucket/image.jpg",
                is_video=False,
            )

            mock_async_session.__aenter__.assert_awaited_once()
            mock_async_session.__aexit__.assert_awaited_once()
            mock_async_session.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_get_db_async_usage(self) -> None:
        """The function must NOT use get_db_async() generator (leak-prone pattern)."""
        import inspect

        from services.monitoring_service._implementation import (
            _rerun_monitoring_analysis_background,
        )

        source = inspect.getsource(_rerun_monitoring_analysis_background)
        assert "get_db_async" not in source, (
            "_rerun_monitoring_analysis_background must use "
            "`async with AsyncSessionLocal()` instead of `get_db_async()` generator"
        )
        assert "async for" not in source, (
            "_rerun_monitoring_analysis_background must not use "
            "`async for session in get_db_async()` pattern"
        )


class TestMonitoringServiceTaskGC:
    """Verify monitoring service stores task references to prevent GC."""

    def test_background_tasks_set_exists(self) -> None:
        """Module must have a set to store background task references."""
        import services.monitoring_service._implementation as monitoring_module

        assert hasattr(monitoring_module, "_background_tasks"), (
            "monitoring_service/_implementation.py must define "
            "`_background_tasks: set[asyncio.Task]`"
        )

    def test_no_bare_create_task_for_rerun(self) -> None:
        """create_task for rerun must store the returned task reference."""
        import inspect

        import services.monitoring_service._implementation as monitoring_module

        source = inspect.getsource(monitoring_module)
        lines = source.split("\n")

        for i, line in enumerate(lines):
            stripped = line.strip()
            if (
                stripped.startswith("asyncio.create_task(")
                and "_rerun_monitoring" in stripped
                and "=" not in line
            ):
                pytest.fail(
                    f"Line {i+1}: bare `asyncio.create_task()` for rerun "
                    "without storing reference."
                )

    @pytest.mark.asyncio
    async def test_schedule_background_task_tracks_and_cleans_up(self) -> None:
        """_schedule_background_task adds task to set and removes on completion."""
        from services.monitoring_service._implementation import (
            _background_tasks,
            _schedule_background_task,
        )

        completed = False

        async def dummy() -> None:
            nonlocal completed
            completed = True

        initial_count = len(_background_tasks)
        _schedule_background_task(dummy(), name="test-task")

        # Task should be tracked
        assert len(_background_tasks) == initial_count + 1

        # Wait for the task to finish deterministically
        pending = [t for t in _background_tasks if t.get_name() == "test-task"]
        if pending:
            await asyncio.wait_for(pending[0], timeout=1)

        assert completed
        assert len(_background_tasks) == initial_count

    @pytest.mark.asyncio
    async def test_schedule_background_task_logs_on_failure(self) -> None:
        """_schedule_background_task logs exception when task fails."""
        from services.monitoring_service._implementation import (
            _background_tasks,
            _schedule_background_task,
        )

        async def failing() -> None:
            raise RuntimeError("test error")

        initial_count = len(_background_tasks)

        with patch("services.monitoring_service._implementation.logger") as mock_logger:
            _schedule_background_task(failing(), name="test-failing")

            pending = [t for t in _background_tasks if t.get_name() == "test-failing"]
            if pending:
                with pytest.raises(RuntimeError):
                    await asyncio.wait_for(pending[0], timeout=1)

            # Task should be cleaned up
            assert len(_background_tasks) == initial_count
            # Exception should be logged
            mock_logger.exception.assert_called_once()
            call_args = mock_logger.exception.call_args
            assert "test-failing" in str(call_args)

    @pytest.mark.asyncio
    async def test_schedule_background_task_cancelled_no_log(self) -> None:
        """_schedule_background_task does not log when task is cancelled."""
        from services.monitoring_service._implementation import (
            _background_tasks,
            _schedule_background_task,
        )

        async def slow() -> None:
            await asyncio.sleep(10)

        initial_count = len(_background_tasks)

        with patch("services.monitoring_service._implementation.logger") as mock_logger:
            _schedule_background_task(slow(), name="test-cancel")

            pending = [t for t in _background_tasks if t.get_name() == "test-cancel"]
            assert len(pending) == 1
            pending[0].cancel()

            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(pending[0], timeout=1)

            assert len(_background_tasks) == initial_count
            mock_logger.exception.assert_not_called()

    @pytest.mark.asyncio
    async def test_fatal_error_emits_statsd_metric(
        self,
        mock_async_session: AsyncMock,
    ) -> None:
        """Fatal error (session creation failure) emits statsd counter."""
        run_id = uuid.uuid4()
        config_id = uuid.uuid4()

        with (
            patch(
                "db.session.AsyncSessionLocal",
                side_effect=RuntimeError("connection refused"),
            ),
            patch("utils.dd.statsd") as mock_statsd,
        ):
            from services.monitoring_service._implementation import (
                _rerun_monitoring_analysis_background,
            )

            await _rerun_monitoring_analysis_background(
                run_id=run_id,
                monitoring_config_id=config_id,
                media_url="s3://bucket/image.jpg",
                is_video=False,
            )

            mock_statsd.increment.assert_called_once()
            call_args = mock_statsd.increment.call_args
            assert call_args[0][0] == "monitoring.rerun.fatal_error"
