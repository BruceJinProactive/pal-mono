"""Tests for eval API routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

EVAL_PREFIX = "/v1/eval"


def _make_mock_run(
    run_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    run_status: str = "pending",
) -> MagicMock:
    run = MagicMock()
    run.id = run_id or uuid.uuid4()
    run.project_id = project_id or uuid.uuid4()
    run.account_id = uuid.uuid4()
    run.status = run_status
    run.driver_mode = "http"
    run.triggered_by = "api"
    run.scenario_count = None
    run.passed_count = None
    run.failed_count = None
    run.overall_score = None
    run.error_message = None
    run.started_at = None
    run.completed_at = None
    run.created_at = datetime.now(timezone.utc)
    return run


def _make_mock_result(
    eval_run_id: uuid.UUID,
    metric_name: str = "tool_call_verification",
    score: float = 1.0,
    passed: bool = True,
) -> MagicMock:
    result = MagicMock()
    result.id = uuid.uuid4()
    result.eval_run_id = eval_run_id
    result.scenario_id = "test_scenario"
    result.metric_name = metric_name
    result.score = score
    result.passed = passed
    result.reason = "All tool calls matched"
    result.raw_output = None
    return result


class TestTriggerEvalRun:
    """Tests for POST /v1/eval/run."""

    @patch("api.routes.eval._implementation.create_eval_run", new_callable=AsyncMock)
    def test_trigger_returns_202(self, mock_create: AsyncMock) -> None:
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()
        mock_run = _make_mock_run(project_id=project_id)
        mock_create.return_value = mock_run

        response = client.post(
            f"{EVAL_PREFIX}/run",
            json={
                "project_id": str(project_id),
                "account_id": str(account_id),
                "driver": "http",
                "triggered_by": "api",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["id"] == str(mock_run.id)
        assert data["status"] == "pending"

    @patch("api.routes.eval._implementation.create_eval_run", new_callable=AsyncMock)
    def test_trigger_with_direct_driver(self, mock_create: AsyncMock) -> None:
        project_id = uuid.uuid4()
        account_id = uuid.uuid4()
        mock_run = _make_mock_run(project_id=project_id)
        mock_run.driver_mode = "direct"
        mock_create.return_value = mock_run

        response = client.post(
            f"{EVAL_PREFIX}/run",
            json={
                "project_id": str(project_id),
                "account_id": str(account_id),
                "driver": "direct",
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["driver_mode"] == "direct"


class TestGetEvalRun:
    """Tests for GET /v1/eval/runs/{run_id}."""

    @patch("api.routes.eval._implementation.get_eval_results", new_callable=AsyncMock)
    @patch("api.routes.eval._implementation.get_eval_run", new_callable=AsyncMock)
    def test_get_run_with_results(
        self, mock_get_run: AsyncMock, mock_get_results: AsyncMock
    ) -> None:
        run_id = uuid.uuid4()
        mock_run = _make_mock_run(run_id=run_id, run_status="completed")
        mock_run.scenario_count = 5
        mock_run.passed_count = 4
        mock_run.failed_count = 1
        mock_run.overall_score = 0.8
        mock_get_run.return_value = mock_run

        mock_result = _make_mock_result(run_id)
        mock_get_results.return_value = [mock_result]

        response = client.get(f"{EVAL_PREFIX}/runs/{run_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["run"]["id"] == str(run_id)
        assert data["run"]["status"] == "completed"
        assert len(data["results"]) == 1
        assert data["results"][0]["metric_name"] == "tool_call_verification"

    @patch("api.routes.eval._implementation.get_eval_run", new_callable=AsyncMock)
    def test_get_run_not_found(self, mock_get_run: AsyncMock) -> None:
        mock_get_run.return_value = None
        run_id = uuid.uuid4()

        response = client.get(f"{EVAL_PREFIX}/runs/{run_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGetScorecard:
    """Tests for GET /v1/eval/scorecard/{project_id}."""

    @patch("api.routes.eval._implementation.get_scorecard", new_callable=AsyncMock)
    def test_get_scorecard(self, mock_scorecard: AsyncMock) -> None:
        project_id = uuid.uuid4()
        mock_scorecard.return_value = {
            "project_id": str(project_id),
            "runs": [
                {
                    "run_id": str(uuid.uuid4()),
                    "status": "completed",
                    "overall_score": 0.9,
                    "scenario_count": 10,
                    "passed_count": 9,
                    "failed_count": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "metrics": {
                        "tool_call_verification": {
                            "avg_score": 0.95,
                            "pass_rate": 0.9,
                        }
                    },
                }
            ],
        }

        response = client.get(f"{EVAL_PREFIX}/scorecard/{project_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["project_id"] == str(project_id)
        assert len(data["runs"]) == 1
        assert data["runs"][0]["overall_score"] == 0.9

    @patch("api.routes.eval._implementation.get_scorecard", new_callable=AsyncMock)
    def test_get_scorecard_with_limit(self, mock_scorecard: AsyncMock) -> None:
        project_id = uuid.uuid4()
        mock_scorecard.return_value = {
            "project_id": str(project_id),
            "runs": [],
        }

        response = client.get(f"{EVAL_PREFIX}/scorecard/{project_id}?limit=5")

        assert response.status_code == status.HTTP_200_OK
        mock_scorecard.assert_called_once()
        call_kwargs = mock_scorecard.call_args
        assert call_kwargs.kwargs["limit"] == 5

    def test_get_scorecard_rejects_zero_limit(self) -> None:
        project_id = uuid.uuid4()
        response = client.get(f"{EVAL_PREFIX}/scorecard/{project_id}?limit=0")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_get_scorecard_rejects_negative_limit(self) -> None:
        project_id = uuid.uuid4()
        response = client.get(f"{EVAL_PREFIX}/scorecard/{project_id}?limit=-1")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
