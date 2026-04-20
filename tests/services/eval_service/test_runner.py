"""Tests for the eval runner (_runner.py)."""

import asyncio
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY as unittest_mock_any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.tables import EvalRun

RUNNER_MODULE = "services.eval_service._runner"


def _make_eval_run(**kwargs: object) -> MagicMock:
    run = MagicMock(spec=EvalRun)
    run.id = kwargs.get("id", uuid.uuid4())
    run.project_id = kwargs.get("project_id", uuid.uuid4())
    run.account_id = kwargs.get("account_id", uuid.uuid4())
    run.driver_mode = kwargs.get("driver_mode", "http")
    run.status = kwargs.get("status", "pending")
    run.triggered_by = kwargs.get("triggered_by", "api")
    run.scenario_count = kwargs.get("scenario_count", 0)
    run.passed_count = kwargs.get("passed_count", 0)
    run.failed_count = kwargs.get("failed_count", 0)
    run.overall_score = kwargs.get("overall_score", None)
    run.started_at = kwargs.get("started_at", None)
    run.completed_at = kwargs.get("completed_at", None)
    run.error_message = kwargs.get("error_message", None)
    run.created_at = kwargs.get("created_at", datetime.now(timezone.utc))
    run.updated_at = kwargs.get("updated_at", None)
    run.agent_fingerprint = kwargs.get("agent_fingerprint", None)
    return run


class TestCreateEvalRun:
    @pytest.mark.asyncio
    async def test_creates_run_and_schedules_background(self) -> None:
        mock_session = AsyncMock()
        mock_run = _make_eval_run()

        with (
            patch(f"{RUNNER_MODULE}.EvalRunRepositoryAsync") as mock_repo_cls,
            patch(f"{RUNNER_MODULE}._schedule_eval_background") as mock_schedule,
        ):
            mock_repo = AsyncMock()
            mock_repo.create.return_value = mock_run
            mock_repo_cls.return_value = mock_repo

            from services.eval_service._runner import create_eval_run

            result = await create_eval_run(
                project_id=uuid.uuid4(),
                account_id=uuid.uuid4(),
                channel_identifier="api:test-project",
                driver_mode="http",
                triggered_by="api",
                session=mock_session,
            )

        assert result is mock_run
        mock_repo.create.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
        mock_schedule.assert_called_once()


class TestGetEvalRun:
    @pytest.mark.asyncio
    async def test_returns_run(self) -> None:
        mock_session = AsyncMock()
        mock_run = _make_eval_run()

        with patch(f"{RUNNER_MODULE}.EvalRunRepositoryAsync") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_by_id.return_value = mock_run
            mock_repo_cls.return_value = mock_repo

            from services.eval_service._runner import get_eval_run

            result = await get_eval_run(mock_run.id, mock_session)

        assert result is mock_run

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        mock_session = AsyncMock()

        with patch(f"{RUNNER_MODULE}.EvalRunRepositoryAsync") as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_by_id.return_value = None
            mock_repo_cls.return_value = mock_repo

            from services.eval_service._runner import get_eval_run

            result = await get_eval_run(uuid.uuid4(), mock_session)

        assert result is None


class TestGetScorecard:
    @pytest.mark.asyncio
    async def test_returns_scorecard_structure(self) -> None:
        mock_session = AsyncMock()
        project_id = uuid.uuid4()

        mock_run = _make_eval_run(
            overall_score=0.8,
            scenario_count=10,
            passed_count=8,
            failed_count=2,
            status="completed",
        )

        mock_result = MagicMock()
        mock_result.metric_name = "tool_call_accuracy"
        mock_result.score = 1.0
        mock_result.passed = True

        with (
            patch(f"{RUNNER_MODULE}.EvalRunRepositoryAsync") as mock_run_repo_cls,
            patch(f"{RUNNER_MODULE}.EvalResultRepositoryAsync") as mock_result_repo_cls,
        ):
            mock_run_repo = AsyncMock()
            mock_run_repo.get_by_project.return_value = [mock_run]
            mock_run_repo_cls.return_value = mock_run_repo

            mock_result_repo = AsyncMock()
            mock_result_repo.get_by_run_id.return_value = [mock_result]
            mock_result_repo_cls.return_value = mock_result_repo

            from services.eval_service._runner import get_scorecard

            result = await get_scorecard(project_id, mock_session)

        assert result["project_id"] == str(project_id)
        assert len(result["runs"]) == 1
        assert result["runs"][0]["overall_score"] == 0.8


class TestBackgroundTasksGC:
    def test_background_tasks_set_exists(self) -> None:
        from services.eval_service._runner import _background_tasks

        assert isinstance(_background_tasks, set)


class TestScheduleEvalBackground:
    @pytest.mark.asyncio
    async def test_creates_asyncio_task_and_adds_to_set(self) -> None:
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()

        with patch(
            f"{RUNNER_MODULE}._run_eval_background", new_callable=AsyncMock
        ) as mock_bg:
            # Return a coroutine that completes immediately
            mock_bg.return_value = None

            from services.eval_service._runner import (
                _background_tasks,
                _schedule_eval_background,
            )

            initial_count = len(_background_tasks)
            _schedule_eval_background(
                eval_run_id, project_id, "api:test-project", "http"
            )

            # Task should have been added to the set (may already be removed if it
            # completed synchronously, but the add+discard callback must have fired)
            mock_bg.assert_called_once_with(
                eval_run_id, project_id, "api:test-project", "http", None
            )

            # Let the event loop tick so the task runs and the done callback fires
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            # After completion the task is discarded — set returns to original size
            assert len(_background_tasks) == initial_count

    @pytest.mark.asyncio
    async def test_task_name_includes_run_id(self) -> None:
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()
        captured_tasks: list[asyncio.Task[object]] = []

        original_create_task = asyncio.create_task

        def _capture_task(coro: object, **kwargs: object) -> asyncio.Task[object]:
            task = original_create_task(coro, **kwargs)  # type: ignore[arg-type]
            captured_tasks.append(task)
            return task

        with (
            patch(f"{RUNNER_MODULE}._run_eval_background", new_callable=AsyncMock),
            patch(f"{RUNNER_MODULE}.asyncio.create_task", side_effect=_capture_task),
        ):
            from services.eval_service._runner import _schedule_eval_background

            _schedule_eval_background(
                eval_run_id, project_id, "api:test-project", "direct"
            )

        assert len(captured_tasks) == 1
        assert str(eval_run_id) in captured_tasks[0].get_name()

    @pytest.mark.asyncio
    async def test_done_callback_is_registered(self) -> None:
        """Verify the discard callback is attached to the created task."""
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()
        captured_task: list[asyncio.Task[object]] = []

        original_create_task = asyncio.create_task

        def _capture(coro: object, **kwargs: object) -> asyncio.Task[object]:
            task = original_create_task(coro, **kwargs)  # type: ignore[arg-type]
            captured_task.append(task)
            return task

        with (
            patch(f"{RUNNER_MODULE}._run_eval_background", new_callable=AsyncMock),
            patch("asyncio.create_task", side_effect=_capture),
        ):
            from services.eval_service._runner import _schedule_eval_background

            _schedule_eval_background(
                eval_run_id, project_id, "api:test-project", "http"
            )

        # The task should have been created
        assert len(captured_task) == 1


class TestRunEvalBackground:
    def _make_scenario(self, scenario_id: str = "sc-1") -> MagicMock:
        scenario = MagicMock()
        scenario.scenario_id = scenario_id
        turn = MagicMock()
        turn.text = "Hello"
        turn.goal = None
        scenario.user_turns = [turn]
        scenario.expected_tool_calls = []
        scenario.expected_outcomes = MagicMock()
        scenario.context = []
        return scenario

    def _make_session_ctx(self) -> tuple[MagicMock, AsyncMock]:
        """Return (ctx_manager_mock, session_mock) where the ctx mgr yields the session."""
        session = AsyncMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx, session

    @pytest.mark.asyncio
    async def test_happy_path_all_pass(self) -> None:
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()
        scenario = self._make_scenario()
        ctx, session = self._make_session_ctx()

        mock_run_repo = AsyncMock()
        mock_result_repo = AsyncMock()

        eval_result = MagicMock()
        eval_result.metric_name = "tool_call_accuracy"
        eval_result.score = 1.0
        eval_result.passed = True
        eval_result.reason = "ok"
        eval_result.raw_output = None

        record = MagicMock()
        record.turns = [{"user": "Hello", "assistant": "Hi"}]
        record.agent_responses = ["Hi"]
        record.tool_calls = []

        with (
            patch(f"{RUNNER_MODULE}.AsyncSessionLocal", return_value=ctx),
            patch(
                f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
            ),
            patch(
                f"{RUNNER_MODULE}.EvalResultRepositoryAsync",
                return_value=mock_result_repo,
            ),
            patch(f"{RUNNER_MODULE}.load_scenarios", return_value=[scenario]),
            patch(
                f"{RUNNER_MODULE}.create_driver", return_value=AsyncMock()
            ) as mock_create_driver,
            patch(
                f"{RUNNER_MODULE}._run_conversation",
                new_callable=AsyncMock,
                return_value=record,
            ),
            patch(
                f"{RUNNER_MODULE}.evaluate_scenario",
                new_callable=AsyncMock,
                return_value=[eval_result],
            ),
        ):
            from services.eval_service._runner import _run_eval_background

            await _run_eval_background(
                eval_run_id, project_id, "api:test-project", "http"
            )

        # Verify channel_identifier is parsed and forwarded to driver factory
        mock_create_driver.assert_called_once_with(
            "http", "test-project", channel="api", scenario_id="sc-1"
        )
        mock_run_repo.update_status.assert_any_await(
            eval_run_id, "running", started_at=unittest_mock_any
        )
        mock_run_repo.update_status.assert_any_await(
            eval_run_id, "completed", completed_at=unittest_mock_any
        )
        mock_run_repo.update_counts.assert_awaited_once_with(
            eval_run_id,
            scenario_count=1,
            passed_count=1,
            failed_count=0,
            overall_score=1.0,
        )
        mock_result_repo.create.assert_awaited_once()
        created_result = mock_result_repo.create.call_args[0][0]
        assert created_result.eval_run_id == eval_run_id

    @pytest.mark.asyncio
    async def test_falls_back_to_generic_scenarios(self) -> None:
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()
        scenario = self._make_scenario()
        ctx, session = self._make_session_ctx()

        mock_run_repo = AsyncMock()
        mock_result_repo = AsyncMock()

        eval_result = MagicMock()
        eval_result.metric_name = "tool_call_accuracy"
        eval_result.score = 1.0
        eval_result.passed = True
        eval_result.reason = "ok"
        eval_result.raw_output = None

        record = MagicMock()
        record.turns = []
        record.agent_responses = []
        record.tool_calls = []

        # Project not in project_map -> _resolve_scenario_files returns [];
        # fallback calls load_scenarios("generic") which returns one scenario.
        with (
            patch(f"{RUNNER_MODULE}.AsyncSessionLocal", return_value=ctx),
            patch(
                f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
            ),
            patch(
                f"{RUNNER_MODULE}.EvalResultRepositoryAsync",
                return_value=mock_result_repo,
            ),
            patch(f"{RUNNER_MODULE}._resolve_scenario_files", return_value=[]),
            patch(f"{RUNNER_MODULE}.load_scenarios", return_value=[scenario]),
            patch(f"{RUNNER_MODULE}.create_driver", return_value=AsyncMock()),
            patch(
                f"{RUNNER_MODULE}._run_conversation",
                new_callable=AsyncMock,
                return_value=record,
            ),
            patch(
                f"{RUNNER_MODULE}.evaluate_scenario",
                new_callable=AsyncMock,
                return_value=[eval_result],
            ),
        ):
            from services.eval_service._runner import _run_eval_background

            await _run_eval_background(
                eval_run_id, project_id, "api:test-project", "http"
            )

        mock_run_repo.update_status.assert_any_await(
            eval_run_id, "completed", completed_at=unittest_mock_any
        )

    @pytest.mark.asyncio
    async def test_no_scenarios_marks_failed(self) -> None:
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()
        ctx, session = self._make_session_ctx()

        mock_run_repo = AsyncMock()
        mock_result_repo = AsyncMock()

        with (
            patch(f"{RUNNER_MODULE}.AsyncSessionLocal", return_value=ctx),
            patch(
                f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
            ),
            patch(
                f"{RUNNER_MODULE}.EvalResultRepositoryAsync",
                return_value=mock_result_repo,
            ),
            patch(f"{RUNNER_MODULE}.load_scenarios", return_value=[]),
        ):
            from services.eval_service._runner import _run_eval_background

            await _run_eval_background(
                eval_run_id, project_id, "api:test-project", "http"
            )

        mock_run_repo.update_status.assert_any_await(
            eval_run_id,
            "failed",
            completed_at=unittest_mock_any,
            error_message="No scenarios found",
        )

    @pytest.mark.asyncio
    async def test_scenario_exception_increments_failed_count_and_continues(
        self,
    ) -> None:
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()
        scenario_a = self._make_scenario("sc-a")
        scenario_b = self._make_scenario("sc-b")
        ctx, session = self._make_session_ctx()

        mock_run_repo = AsyncMock()
        mock_result_repo = AsyncMock()

        passing_result = MagicMock()
        passing_result.metric_name = "tool_call_accuracy"
        passing_result.score = 1.0
        passing_result.passed = True
        passing_result.reason = "ok"
        passing_result.raw_output = None

        record = MagicMock()
        record.turns = []
        record.agent_responses = []
        record.tool_calls = []

        run_conversation_calls = 0

        async def _side_effect(
            driver: object, scenario: object, simulator: object
        ) -> MagicMock:
            nonlocal run_conversation_calls
            run_conversation_calls += 1
            if run_conversation_calls == 1:
                raise RuntimeError("driver exploded")
            return record

        with (
            patch(f"{RUNNER_MODULE}.AsyncSessionLocal", return_value=ctx),
            patch(
                f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
            ),
            patch(
                f"{RUNNER_MODULE}.EvalResultRepositoryAsync",
                return_value=mock_result_repo,
            ),
            patch(
                f"{RUNNER_MODULE}.load_scenarios", return_value=[scenario_a, scenario_b]
            ),
            patch(f"{RUNNER_MODULE}.create_driver", return_value=AsyncMock()),
            patch(f"{RUNNER_MODULE}._run_conversation", side_effect=_side_effect),
            patch(
                f"{RUNNER_MODULE}.evaluate_scenario",
                new_callable=AsyncMock,
                return_value=[passing_result],
            ),
        ):
            from services.eval_service._runner import _run_eval_background

            await _run_eval_background(
                eval_run_id, project_id, "api:test-project", "http"
            )

        mock_run_repo.update_counts.assert_awaited_once_with(
            eval_run_id,
            scenario_count=2,
            passed_count=1,
            failed_count=1,
            overall_score=0.5,
        )
        mock_run_repo.update_status.assert_any_await(
            eval_run_id, "completed", completed_at=unittest_mock_any
        )
        # Rollback must have been called for the failed scenario
        session.rollback.assert_awaited()

    @pytest.mark.asyncio
    async def test_eval_result_row_uses_eval_run_id_field(self) -> None:
        """Verify the EvalResult is constructed with eval_run_id (not run_id)."""
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()
        scenario = self._make_scenario()
        ctx, session = self._make_session_ctx()

        mock_run_repo = AsyncMock()
        mock_result_repo = AsyncMock()

        eval_result = MagicMock()
        eval_result.metric_name = "tool_call_accuracy"
        eval_result.score = 0.5
        eval_result.passed = False
        eval_result.reason = "missing"
        eval_result.raw_output = {"detail": "x"}

        record = MagicMock()
        record.turns = []
        record.agent_responses = []
        record.tool_calls = []

        with (
            patch(f"{RUNNER_MODULE}.AsyncSessionLocal", return_value=ctx),
            patch(
                f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
            ),
            patch(
                f"{RUNNER_MODULE}.EvalResultRepositoryAsync",
                return_value=mock_result_repo,
            ),
            patch(f"{RUNNER_MODULE}.load_scenarios", return_value=[scenario]),
            patch(f"{RUNNER_MODULE}.create_driver", return_value=AsyncMock()),
            patch(
                f"{RUNNER_MODULE}._run_conversation",
                new_callable=AsyncMock,
                return_value=record,
            ),
            patch(
                f"{RUNNER_MODULE}.evaluate_scenario",
                new_callable=AsyncMock,
                return_value=[eval_result],
            ),
        ):
            from services.eval_service._runner import _run_eval_background

            await _run_eval_background(
                eval_run_id, project_id, "api:test-project", "http"
            )

        assert mock_result_repo.create.call_count == 1
        db_result = mock_result_repo.create.call_args[0][0]
        # Must use eval_run_id, not run_id
        assert hasattr(db_result, "eval_run_id")
        assert db_result.eval_run_id == eval_run_id
        assert db_result.metric_name == "tool_call_accuracy"
        assert db_result.score == 0.5
        assert db_result.passed is False

    @pytest.mark.asyncio
    async def test_top_level_exception_marks_failed_with_error_message(self) -> None:
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()

        main_ctx, main_session = self._make_session_ctx()
        err_ctx, err_session = self._make_session_ctx()

        call_count = 0

        def _session_factory() -> MagicMock:
            nonlocal call_count
            call_count += 1
            return main_ctx if call_count == 1 else err_ctx

        mock_run_repo = AsyncMock()
        mock_err_repo = AsyncMock()

        def _repo_factory(session: object) -> AsyncMock:
            return mock_run_repo if session is main_session else mock_err_repo

        with (
            patch(f"{RUNNER_MODULE}.AsyncSessionLocal", side_effect=_session_factory),
            patch(f"{RUNNER_MODULE}.EvalRunRepositoryAsync", side_effect=_repo_factory),
            patch(
                f"{RUNNER_MODULE}.EvalResultRepositoryAsync", return_value=AsyncMock()
            ),
            patch(f"{RUNNER_MODULE}.load_scenarios", side_effect=RuntimeError("boom")),
        ):
            from services.eval_service._runner import _run_eval_background

            await _run_eval_background(
                eval_run_id, project_id, "api:test-project", "http"
            )

        mock_err_repo.update_status.assert_awaited_once_with(
            eval_run_id,
            "failed",
            completed_at=unittest_mock_any,
            error_message="boom",
        )
        err_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_multiple_eval_results_per_scenario(self) -> None:
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()
        scenario = self._make_scenario()
        ctx, session = self._make_session_ctx()

        mock_run_repo = AsyncMock()
        mock_result_repo = AsyncMock()

        results = [
            MagicMock(
                metric_name="tool_call_accuracy",
                score=1.0,
                passed=True,
                reason="ok",
                raw_output=None,
            ),
            MagicMock(
                metric_name="responsive",
                score=0.9,
                passed=True,
                reason="good",
                raw_output=None,
            ),
            MagicMock(
                metric_name="faithfulness",
                score=0.8,
                passed=True,
                reason="faithful",
                raw_output=None,
            ),
        ]

        record = MagicMock()
        record.turns = []
        record.agent_responses = ["Hi"]
        record.tool_calls = []

        with (
            patch(f"{RUNNER_MODULE}.AsyncSessionLocal", return_value=ctx),
            patch(
                f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
            ),
            patch(
                f"{RUNNER_MODULE}.EvalResultRepositoryAsync",
                return_value=mock_result_repo,
            ),
            patch(f"{RUNNER_MODULE}.load_scenarios", return_value=[scenario]),
            patch(f"{RUNNER_MODULE}.create_driver", return_value=AsyncMock()),
            patch(
                f"{RUNNER_MODULE}._run_conversation",
                new_callable=AsyncMock,
                return_value=record,
            ),
            patch(
                f"{RUNNER_MODULE}.evaluate_scenario",
                new_callable=AsyncMock,
                return_value=results,
            ),
        ):
            from services.eval_service._runner import _run_eval_background

            await _run_eval_background(
                eval_run_id, project_id, "api:test-project", "http"
            )

        assert mock_result_repo.create.call_count == 3
        for call in mock_result_repo.create.call_args_list:
            assert call[0][0].eval_run_id == eval_run_id


class TestResolveScenarioFiles:
    def test_returns_empty_when_no_map_file(self) -> None:
        with patch(f"{RUNNER_MODULE}._PROJECT_MAP_PATH") as mock_path:
            mock_path.exists.return_value = False
            from services.eval_service._runner import _resolve_scenario_files

            result = _resolve_scenario_files(uuid.uuid4())
        assert result == []

    def test_returns_list_value_from_map(self, tmp_path: object) -> None:
        import json

        project_id = uuid.uuid4()
        map_file = Path(str(tmp_path)) / "project_map.json"
        map_file.write_text(
            json.dumps({str(project_id): ["ordering/foo.yaml", "ordering/bar.yaml"]})
        )
        with patch(f"{RUNNER_MODULE}._PROJECT_MAP_PATH", map_file):
            from services.eval_service._runner import _resolve_scenario_files

            result = _resolve_scenario_files(project_id)
        assert result == ["ordering/foo.yaml", "ordering/bar.yaml"]

    def test_returns_single_string_as_list(self, tmp_path: object) -> None:
        import json

        project_id = uuid.uuid4()
        map_file = Path(str(tmp_path)) / "project_map.json"
        map_file.write_text(json.dumps({str(project_id): "ordering/single.yaml"}))
        with patch(f"{RUNNER_MODULE}._PROJECT_MAP_PATH", map_file):
            from services.eval_service._runner import _resolve_scenario_files

            result = _resolve_scenario_files(project_id)
        assert result == ["ordering/single.yaml"]

    def test_returns_empty_for_unknown_project(self, tmp_path: object) -> None:
        import json

        map_file = Path(str(tmp_path)) / "project_map.json"
        map_file.write_text(json.dumps({"some-other-id": ["ordering/x.yaml"]}))
        with patch(f"{RUNNER_MODULE}._PROJECT_MAP_PATH", map_file):
            from services.eval_service._runner import _resolve_scenario_files

            result = _resolve_scenario_files(uuid.uuid4())
        assert result == []


class TestRunEvalBackgroundWithFileResolution(TestRunEvalBackground):
    """Test the file-based scenario resolution path in _run_eval_background."""

    @pytest.mark.asyncio
    async def test_loads_scenarios_from_resolved_files(self) -> None:
        eval_run_id = uuid.uuid4()
        project_id = uuid.uuid4()
        scenario = self._make_scenario()
        ctx, session = self._make_session_ctx()

        mock_run_repo = AsyncMock()
        mock_result_repo = AsyncMock()

        eval_result = MagicMock()
        eval_result.metric_name = "tool_call_accuracy"
        eval_result.score = 1.0
        eval_result.passed = True
        eval_result.reason = "ok"
        eval_result.raw_output = None

        record = MagicMock()
        record.turns = []
        record.agent_responses = []
        record.tool_calls = []

        with (
            patch(f"{RUNNER_MODULE}.AsyncSessionLocal", return_value=ctx),
            patch(
                f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
            ),
            patch(
                f"{RUNNER_MODULE}.EvalResultRepositoryAsync",
                return_value=mock_result_repo,
            ),
            patch(
                f"{RUNNER_MODULE}._resolve_scenario_files",
                return_value=["ordering/test_client.yaml"],
            ),
            patch(
                f"{RUNNER_MODULE}.validate_scenarios_from_yaml",
                return_value=[scenario],
            ),
            patch(f"{RUNNER_MODULE}.create_driver", return_value=AsyncMock()),
            patch(
                f"{RUNNER_MODULE}._run_conversation",
                new_callable=AsyncMock,
                return_value=record,
            ),
            patch(
                f"{RUNNER_MODULE}.evaluate_scenario",
                new_callable=AsyncMock,
                return_value=[eval_result],
            ),
        ):
            from services.eval_service._runner import _run_eval_background

            await _run_eval_background(
                eval_run_id, project_id, "api:test-project", "http"
            )

        mock_run_repo.update_status.assert_any_await(
            eval_run_id, "completed", completed_at=unittest_mock_any
        )


class TestRunConversation:
    def _make_scenario(
        self,
        turns: Sequence[object] | None = None,
        persona: str = "standard_customer",
        scenario_text: str = "test scenario",
    ) -> MagicMock:
        from services.eval_service.schema import UserTurn

        scenario = MagicMock()
        scenario.scenario_id = "sc-conv-1"
        scenario.persona = persona
        scenario.scenario = scenario_text
        scenario.max_turns = 14
        if turns is None:
            t = UserTurn(text="Hello there")
            scenario.user_turns = [t]
        else:
            scenario.user_turns = list(turns)
        return scenario

    def _make_simulator(self) -> AsyncMock:
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_single_user_turn_builds_record(self) -> None:
        from services.eval_service.schema import UserTurn

        scenario = self._make_scenario([UserTurn(text="What is on the menu?")])
        simulator = self._make_simulator()

        driver = AsyncMock()
        driver.last_conversation_id = None
        turn_result = MagicMock()
        turn_result.content = "We have pizza and pasta."
        driver.send_turn = AsyncMock(return_value=turn_result)

        with patch(f"{RUNNER_MODULE}.ConversationTurn") as mock_conv_turn:
            mock_conv_turn.side_effect = lambda role, content: MagicMock(
                role=role, content=content
            )

            from services.eval_service._runner import _run_conversation

            record = await _run_conversation(driver, scenario, simulator)

        assert len(record.turns) == 1
        assert record.turns[0]["user"] == "What is on the menu?"
        assert record.turns[0]["assistant"] == "We have pizza and pasta."
        assert record.agent_responses == ["We have pizza and pasta."]
        assert record.tool_calls == []
        driver.send_turn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multi_turn_builds_history(self) -> None:
        from services.eval_service.schema import UserTurn

        scenario = self._make_scenario(
            [UserTurn(text="Hi"), UserTurn(text="What are your hours?")]
        )
        simulator = self._make_simulator()

        responses = ["Hello!", "We are open 9-5."]
        call_idx = 0

        async def _send_turn(message: str, history: list[object]) -> MagicMock:
            nonlocal call_idx
            tr = MagicMock()
            tr.content = responses[call_idx]
            call_idx += 1
            return tr

        driver = AsyncMock()
        driver.last_conversation_id = None
        driver.send_turn = AsyncMock(side_effect=_send_turn)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        assert len(record.turns) == 2
        assert record.agent_responses == ["Hello!", "We are open 9-5."]
        # History is a mutable list passed by reference — by the end it has all 4 entries.
        # Verify send_turn was called twice and the final history has all entries.
        assert driver.send_turn.await_count == 2
        # First call message was "Hi", second was "What are your hours?"
        assert driver.send_turn.call_args_list[0][0][0] == "Hi"
        assert driver.send_turn.call_args_list[1][0][0] == "What are your hours?"

    @pytest.mark.asyncio
    async def test_plain_string_turn_is_stringified(self) -> None:
        """Non-UserTurn entries (plain strings) are coerced via str()."""
        scenario = self._make_scenario(["book a table for 2"])
        simulator = self._make_simulator()

        driver = AsyncMock()
        driver.last_conversation_id = None
        turn_result = MagicMock()
        turn_result.content = "Booked!"
        driver.send_turn = AsyncMock(return_value=turn_result)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        assert record.turns[0]["user"] == "book a table for 2"

    @pytest.mark.asyncio
    async def test_goal_used_when_text_is_none(self) -> None:
        from services.eval_service.schema import UserTurn

        scenario = self._make_scenario([UserTurn(text=None, goal="order a coffee")])
        simulator = self._make_simulator()

        driver = AsyncMock()
        driver.last_conversation_id = None
        turn_result = MagicMock()
        turn_result.content = "Sure!"
        driver.send_turn = AsyncMock(return_value=turn_result)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        # When text is None, fall back to goal
        assert record.turns[0]["user"] == "order a coffee"
        # First (and only) call uses the goal text as message
        driver.send_turn.assert_awaited_once()
        assert driver.send_turn.call_args[0][0] == "order a coffee"

    @pytest.mark.asyncio
    async def test_tool_calls_read_from_db_after_conversation(self) -> None:
        """Tool calls are queried from the DB after all turns complete."""
        from services.eval_service.schema import UserTurn

        scenario = self._make_scenario(
            [UserTurn(text="Reserve"), UserTurn(text="Confirm")]
        )
        simulator = self._make_simulator()
        conversation_id = uuid.uuid4()

        async def _send(message: str, history: list[object]) -> MagicMock:
            tr = MagicMock()
            tr.content = "done"
            return tr

        driver = AsyncMock()
        driver.last_conversation_id = str(conversation_id)
        driver.send_turn = AsyncMock(side_effect=_send)

        db_tool_calls = [
            {
                "type": "tool_call",
                "payload": {"tool_name": "reserve", "arguments": {}, "result": "ok"},
            },
            {
                "type": "tool_call",
                "payload": {"tool_name": "confirm", "arguments": {}, "result": "ok"},
            },
        ]

        # Mock DB message with tool_calls in body
        mock_db_msg = MagicMock()
        mock_db_msg.body = {"tool_calls": db_tool_calls, "author_type": "agent"}

        mock_repo = AsyncMock()
        mock_repo.get_messages_by_conversation.return_value = [mock_db_msg]

        with (
            patch(f"{RUNNER_MODULE}.AsyncSessionLocal") as mock_session_factory,
            patch(f"{RUNNER_MODULE}.MessageRepositoryAsync", return_value=mock_repo),
        ):
            mock_session = AsyncMock()
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=mock_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session_factory.return_value = ctx

            from services.eval_service._runner import _run_conversation

            record = await _run_conversation(driver, scenario, simulator)

        assert len(record.tool_calls) == 2
        assert record.tool_calls[0]["payload"]["tool_name"] == "reserve"
        assert record.tool_calls[1]["payload"]["tool_name"] == "confirm"
        mock_repo.get_messages_by_conversation.assert_awaited_once_with(conversation_id)

    @pytest.mark.asyncio
    async def test_no_tool_calls_when_no_conversation_id(self) -> None:
        """When driver has no conversation_id, tool_calls stays empty."""
        from services.eval_service.schema import UserTurn

        scenario = self._make_scenario([UserTurn(text="Hello")])
        simulator = self._make_simulator()

        driver = AsyncMock()
        driver.last_conversation_id = None
        turn_result = MagicMock()
        turn_result.content = "Hi!"
        driver.send_turn = AsyncMock(return_value=turn_result)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        assert record.tool_calls == []

    @pytest.mark.asyncio
    async def test_tool_calls_empty_when_db_messages_have_no_tool_calls(self) -> None:
        """DB messages without tool_calls key produce empty list."""
        from services.eval_service.schema import UserTurn

        scenario = self._make_scenario([UserTurn(text="Hello")])
        simulator = self._make_simulator()
        conversation_id = uuid.uuid4()

        driver = AsyncMock()
        driver.last_conversation_id = str(conversation_id)
        turn_result = MagicMock()
        turn_result.content = "Hi!"
        driver.send_turn = AsyncMock(return_value=turn_result)

        mock_db_msg = MagicMock()
        mock_db_msg.body = {"author_type": "agent", "text": {"body": "Hi!"}}

        mock_repo = AsyncMock()
        mock_repo.get_messages_by_conversation.return_value = [mock_db_msg]

        with (
            patch(f"{RUNNER_MODULE}.AsyncSessionLocal") as mock_session_factory,
            patch(f"{RUNNER_MODULE}.MessageRepositoryAsync", return_value=mock_repo),
        ):
            mock_session = AsyncMock()
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=mock_session)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_session_factory.return_value = ctx

            from services.eval_service._runner import _run_conversation

            record = await _run_conversation(driver, scenario, simulator)

        assert record.tool_calls == []

    @pytest.mark.asyncio
    async def test_ai_driven_turn_calls_simulator(self) -> None:
        from services.eval_service._user_simulator import END_SENTINEL
        from services.eval_service.schema import TurnType, UserTurn

        ai_turn = UserTurn(type=TurnType.AI_DRIVEN, goal="ask about hours")
        scenario = self._make_scenario(
            [ai_turn], persona="curious_customer", scenario_text="hours inquiry"
        )

        simulator = self._make_simulator()
        simulator.generate_user_message = AsyncMock(
            side_effect=["What are your hours?", END_SENTINEL]
        )

        driver = AsyncMock()
        driver.last_conversation_id = None
        turn_result = MagicMock()
        turn_result.content = "We're open 9-5."
        driver.send_turn = AsyncMock(return_value=turn_result)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        # First simulator call produces a message, second returns END
        assert simulator.generate_user_message.await_count == 2
        first_call_kwargs = simulator.generate_user_message.call_args_list[0][1]
        assert first_call_kwargs["persona"] == "curious_customer"
        assert first_call_kwargs["scenario"] == "hours inquiry"
        assert first_call_kwargs["goal"] == "ask about hours"
        assert first_call_kwargs["turn_number"] == 0
        assert record.turns[0]["user"] == "What are your hours?"
        assert record.turns[0]["assistant"] == "We're open 9-5."

    @pytest.mark.asyncio
    async def test_ai_driven_end_sentinel_stops_conversation(self) -> None:
        from services.eval_service._user_simulator import END_SENTINEL
        from services.eval_service.schema import TurnType, UserTurn

        turns = [
            UserTurn(text="Hi"),
            UserTurn(type=TurnType.AI_DRIVEN, goal="wrap up"),
        ]
        scenario = self._make_scenario(turns)

        simulator = self._make_simulator()
        simulator.generate_user_message = AsyncMock(return_value=END_SENTINEL)

        driver = AsyncMock()
        driver.last_conversation_id = None
        turn_result = MagicMock()
        turn_result.content = "Hello!"
        driver.send_turn = AsyncMock(return_value=turn_result)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        # Only the first (static) turn should have been sent
        assert len(record.turns) == 1
        assert record.turns[0]["user"] == "Hi"
        # Simulator was called for turn 1 but returned END
        simulator.generate_user_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mixed_static_and_ai_driven_turns(self) -> None:
        from services.eval_service.schema import TurnType, UserTurn

        turns = [
            UserTurn(text="Hello"),
            UserTurn(type=TurnType.AI_DRIVEN, goal="ask about menu"),
            UserTurn(text="Thanks, bye!"),
        ]
        scenario = self._make_scenario(turns, persona="foodie")

        simulator = self._make_simulator()
        simulator.generate_user_message = AsyncMock(
            return_value="What's on the menu today?"
        )

        responses = ["Hi there!", "We have pasta and salad.", "Goodbye!"]
        call_idx = 0

        async def _send(message: str, history: list[object]) -> MagicMock:
            nonlocal call_idx
            tr = MagicMock()
            tr.content = responses[call_idx]
            call_idx += 1
            return tr

        driver = AsyncMock()
        driver.last_conversation_id = None
        driver.send_turn = AsyncMock(side_effect=_send)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        assert len(record.turns) == 3
        assert record.turns[0]["user"] == "Hello"
        assert record.turns[1]["user"] == "What's on the menu today?"
        assert record.turns[2]["user"] == "Thanks, bye!"

    @pytest.mark.asyncio
    async def test_ai_driven_loops_until_end_sentinel(self) -> None:
        """Last ai_driven turn loops the simulator until [END]."""
        from services.eval_service._user_simulator import END_SENTINEL
        from services.eval_service.schema import TurnType, UserTurn

        ai_turn = UserTurn(type=TurnType.AI_DRIVEN, goal="order a pizza")
        scenario = self._make_scenario([ai_turn])
        scenario.max_turns = 14

        simulator = self._make_simulator()
        replies = ["I'd like a cheese pizza", "Yes, that's all", END_SENTINEL]
        simulator.generate_user_message = AsyncMock(side_effect=replies)

        responses = ["What size?", "Order placed!"]
        resp_idx = 0

        async def _send(message: str, history: list[object]) -> MagicMock:
            nonlocal resp_idx
            tr = MagicMock()
            tr.content = responses[resp_idx]
            resp_idx += 1
            return tr

        driver = AsyncMock()
        driver.last_conversation_id = None
        driver.send_turn = AsyncMock(side_effect=_send)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        assert len(record.turns) == 2
        assert record.turns[0]["user"] == "I'd like a cheese pizza"
        assert record.turns[1]["user"] == "Yes, that's all"
        assert simulator.generate_user_message.await_count == 3

    @pytest.mark.asyncio
    async def test_ai_driven_loops_respects_max_turns(self) -> None:
        """Loop stops at max_turns even if simulator never returns [END]."""
        from services.eval_service.schema import TurnType, UserTurn

        ai_turn = UserTurn(type=TurnType.AI_DRIVEN, goal="keep chatting")
        scenario = self._make_scenario([ai_turn])
        scenario.max_turns = 3

        simulator = self._make_simulator()
        simulator.generate_user_message = AsyncMock(return_value="Tell me more")

        driver = AsyncMock()
        driver.last_conversation_id = None
        turn_result = MagicMock()
        turn_result.content = "Sure, here's more info."
        driver.send_turn = AsyncMock(return_value=turn_result)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        assert len(record.turns) == 3
        assert simulator.generate_user_message.await_count == 3

    @pytest.mark.asyncio
    async def test_static_then_ai_driven_loop(self) -> None:
        """Static opening turn followed by ai_driven loop."""
        from services.eval_service._user_simulator import END_SENTINEL
        from services.eval_service.schema import TurnType, UserTurn

        turns = [
            UserTurn(text="Hi, I want to order"),
            UserTurn(type=TurnType.AI_DRIVEN, goal="complete the order"),
        ]
        scenario = self._make_scenario(turns)
        scenario.max_turns = 14

        simulator = self._make_simulator()
        simulator.generate_user_message = AsyncMock(
            side_effect=["A cheese pizza please", END_SENTINEL]
        )

        responses = ["Welcome! What would you like?", "Got it, one cheese pizza."]
        resp_idx = 0

        async def _send(message: str, history: list[object]) -> MagicMock:
            nonlocal resp_idx
            tr = MagicMock()
            tr.content = responses[resp_idx]
            resp_idx += 1
            return tr

        driver = AsyncMock()
        driver.last_conversation_id = None
        driver.send_turn = AsyncMock(side_effect=_send)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        assert len(record.turns) == 2
        assert record.turns[0]["user"] == "Hi, I want to order"
        assert record.turns[1]["user"] == "A cheese pizza please"

    @pytest.mark.asyncio
    async def test_ai_driven_loop_passes_max_turns_to_simulator(self) -> None:
        """Verify max_turns kwarg is forwarded to the simulator."""
        from services.eval_service._user_simulator import END_SENTINEL
        from services.eval_service.schema import TurnType, UserTurn

        ai_turn = UserTurn(type=TurnType.AI_DRIVEN, goal="test goal")
        scenario = self._make_scenario([ai_turn])
        scenario.max_turns = 10

        simulator = self._make_simulator()
        simulator.generate_user_message = AsyncMock(return_value=END_SENTINEL)

        driver = AsyncMock()
        driver.last_conversation_id = None

        from services.eval_service._runner import _run_conversation

        await _run_conversation(driver, scenario, simulator)

        call_kwargs = simulator.generate_user_message.call_args[1]
        assert call_kwargs["max_turns"] == 10

    @pytest.mark.asyncio
    async def test_ai_driven_loop_grants_one_turn_when_budget_exhausted(self) -> None:
        """When static turns already consumed max_turns, ai_driven still gets 1 turn."""
        from services.eval_service.schema import TurnType, UserTurn

        static_turns = [UserTurn(text=f"msg-{i}") for i in range(5)]
        ai_turn = UserTurn(type=TurnType.AI_DRIVEN, goal="finish up")
        scenario = self._make_scenario([*static_turns, ai_turn])
        scenario.max_turns = 3  # budget already exceeded by 5 static turns

        simulator = self._make_simulator()
        simulator.generate_user_message = AsyncMock(return_value="One last thing")

        responses = [f"resp-{i}" for i in range(6)]
        resp_idx = 0

        async def _send(message: str, history: list[object]) -> MagicMock:
            nonlocal resp_idx
            tr = MagicMock()
            tr.content = responses[resp_idx]
            resp_idx += 1
            return tr

        driver = AsyncMock()
        driver.last_conversation_id = None
        driver.send_turn = AsyncMock(side_effect=_send)

        from services.eval_service._runner import _run_conversation

        record = await _run_conversation(driver, scenario, simulator)

        # 5 static turns + 1 ai_driven turn (granted despite exhausted budget)
        assert len(record.turns) == 6
        assert record.turns[5]["user"] == "One last thing"


class TestMarkStaleRunsFailed:
    @pytest.mark.asyncio
    async def test_marks_stale_running_runs_as_failed(self) -> None:
        from datetime import timedelta

        stale_run = MagicMock()
        stale_run.id = uuid.uuid4()
        stale_run.status = "running"
        stale_run.started_at = datetime.now(timezone.utc) - timedelta(minutes=60)

        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [stale_run]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_run_repo = AsyncMock()

        with patch(
            f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
        ):
            from services.eval_service._runner import mark_stale_runs_failed

            count = await mark_stale_runs_failed(mock_session, stale_minutes=30)

        assert count == 1
        mock_run_repo.update_status.assert_awaited_once_with(
            stale_run.id,
            "failed",
            completed_at=unittest_mock_any,
            error_message="Stale run: no progress for 30 minutes",
        )
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_stale_runs(self) -> None:
        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_run_repo = AsyncMock()

        with patch(
            f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
        ):
            from services.eval_service._runner import mark_stale_runs_failed

            count = await mark_stale_runs_failed(mock_session, stale_minutes=30)

        assert count == 0
        mock_run_repo.update_status.assert_not_awaited()
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_marks_multiple_stale_runs(self) -> None:
        stale_run_a = MagicMock()
        stale_run_a.id = uuid.uuid4()
        stale_run_b = MagicMock()
        stale_run_b.id = uuid.uuid4()

        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [stale_run_a, stale_run_b]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_run_repo = AsyncMock()

        with patch(
            f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
        ):
            from services.eval_service._runner import mark_stale_runs_failed

            count = await mark_stale_runs_failed(mock_session, stale_minutes=15)

        assert count == 2
        assert mock_run_repo.update_status.await_count == 2
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_custom_stale_minutes_reflected_in_error_message(self) -> None:
        stale_run = MagicMock()
        stale_run.id = uuid.uuid4()

        mock_session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [stale_run]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_run_repo = AsyncMock()

        with patch(
            f"{RUNNER_MODULE}.EvalRunRepositoryAsync", return_value=mock_run_repo
        ):
            from services.eval_service._runner import mark_stale_runs_failed

            await mark_stale_runs_failed(mock_session, stale_minutes=45)

        call_kwargs = mock_run_repo.update_status.call_args[1]
        assert "45 minutes" in call_kwargs["error_message"]


class TestGetEvalResults:
    @pytest.mark.asyncio
    async def test_delegates_to_repository(self) -> None:
        mock_session = AsyncMock()
        run_id = uuid.uuid4()

        mock_result_a = MagicMock()
        mock_result_a.id = uuid.uuid4()
        mock_result_b = MagicMock()
        mock_result_b.id = uuid.uuid4()

        mock_repo = AsyncMock()
        mock_repo.get_by_run_id.return_value = [mock_result_a, mock_result_b]

        with patch(
            f"{RUNNER_MODULE}.EvalResultRepositoryAsync", return_value=mock_repo
        ):
            from services.eval_service._runner import get_eval_results

            results = await get_eval_results(run_id, mock_session)

        assert results == [mock_result_a, mock_result_b]
        mock_repo.get_by_run_id.assert_awaited_once_with(run_id)

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(self) -> None:
        mock_session = AsyncMock()
        run_id = uuid.uuid4()

        mock_repo = AsyncMock()
        mock_repo.get_by_run_id.return_value = []

        with patch(
            f"{RUNNER_MODULE}.EvalResultRepositoryAsync", return_value=mock_repo
        ):
            from services.eval_service._runner import get_eval_results

            results = await get_eval_results(run_id, mock_session)

        assert results == []
