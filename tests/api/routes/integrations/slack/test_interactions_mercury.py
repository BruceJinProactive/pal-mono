"""Tests for Mercury routing in handle_interactions."""

import asyncio
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

import pytest
from fastapi import Request

from api.routes.integrations.slack._interactions import (
    _background_tasks,
    _schedule_background_task,
)


def _build_request(payload: dict) -> Request:
    """Build a mock FastAPI Request with a valid Slack interaction payload."""
    body_str = urlencode({"payload": json.dumps(payload)})
    body_bytes = body_str.encode("utf-8")

    ts = str(int(time.time()))
    secret = "test_signing_secret"
    sig_basestring = f"v0:{ts}:{body_str}"
    sig = (
        "v0="
        + hmac.new(secret.encode(), sig_basestring.encode(), hashlib.sha256).hexdigest()
    )

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [
            (b"x-slack-request-timestamp", ts.encode()),
            (b"x-slack-signature", sig.encode()),
        ],
    }
    request = Request(scope)
    request._body = body_bytes
    return request


@pytest.mark.asyncio
async def test_view_submission_mercury_schedules_handler() -> None:
    payload = {
        "type": "view_submission",
        "view": {
            "callback_id": "mercury_report_submit",
            "state": {
                "values": {
                    "report_period": {
                        "period_value": {"selected_option": {"value": "daily"}}
                    },
                }
            },
            "private_metadata": "C123",
        },
        "user": {"id": "U123", "name": "testuser"},
    }
    request = _build_request(payload)

    mock_handler = AsyncMock(return_value={"ok": True})

    with (
        patch(
            "api.routes.integrations.slack._interactions.get_server_secret_with_fallback",
            return_value="test_signing_secret",
        ),
        patch(
            "api.routes.integrations.slack._interactions.verify_slack_signature",
            return_value=True,
        ),
        patch(
            "api.routes.integrations.slack._mercury_actions.handle_mercury_view_submission",
            mock_handler,
        ),
    ):
        from api.routes.integrations.slack._interactions import handle_interactions

        result = await handle_interactions(request)

        assert result == {"ok": True}
        # Let the background task run
        await asyncio.sleep(0)
        mock_handler.assert_called_once_with(payload)


@pytest.mark.asyncio
async def test_view_submission_non_mercury_returns_ok() -> None:
    payload = {
        "type": "view_submission",
        "view": {"callback_id": "some_other_callback"},
        "user": {"id": "U123"},
    }
    request = _build_request(payload)

    with (
        patch(
            "api.routes.integrations.slack._interactions.get_server_secret_with_fallback",
            return_value="test_signing_secret",
        ),
        patch(
            "api.routes.integrations.slack._interactions.verify_slack_signature",
            return_value=True,
        ),
    ):
        from api.routes.integrations.slack._interactions import handle_interactions

        result = await handle_interactions(request)
        assert result == {"ok": True}


@pytest.mark.asyncio
async def test_block_action_mercury_direct_is_backgrounded() -> None:
    """Direct commands (no modal) are backgrounded since they don't need trigger_id."""
    payload = {
        "type": "block_actions",
        "actions": [{"action_id": "mercury_daily", "value": "mercury_daily"}],
        "channel": {"id": "C123"},
        "user": {"id": "U123", "name": "testuser"},
        "trigger_id": "T123",
    }
    request = _build_request(payload)

    mock_handler = AsyncMock(return_value={"ok": True})

    with (
        patch(
            "api.routes.integrations.slack._interactions.get_server_secret_with_fallback",
            return_value="test_signing_secret",
        ),
        patch(
            "api.routes.integrations.slack._interactions.verify_slack_signature",
            return_value=True,
        ),
        patch(
            "api.routes.integrations.slack._mercury_actions.handle_mercury_block_action",
            mock_handler,
        ),
    ):
        from api.routes.integrations.slack._interactions import handle_interactions

        result = await handle_interactions(request)

        assert result == {"ok": True}
        # Let the background task run
        await asyncio.sleep(0)
        mock_handler.assert_called_once_with(payload, payload["actions"][0])


@pytest.mark.asyncio
async def test_block_action_mercury_modal_opener_is_awaited() -> None:
    """Modal openers must be awaited directly so trigger_id doesn't expire."""
    payload = {
        "type": "block_actions",
        "actions": [{"action_id": "mercury_tool_feedback", "value": "tool_feedback"}],
        "channel": {"id": "C123"},
        "user": {"id": "U123", "name": "testuser"},
        "trigger_id": "T123",
    }
    request = _build_request(payload)

    mock_handler = AsyncMock(return_value={"ok": True})

    with (
        patch(
            "api.routes.integrations.slack._interactions.get_server_secret_with_fallback",
            return_value="test_signing_secret",
        ),
        patch(
            "api.routes.integrations.slack._interactions.verify_slack_signature",
            return_value=True,
        ),
        patch(
            "api.routes.integrations.slack._mercury_actions.handle_mercury_block_action",
            mock_handler,
        ),
    ):
        from api.routes.integrations.slack._interactions import handle_interactions

        result = await handle_interactions(request)

        assert result == {"ok": True}
        # Awaited directly — no sleep needed
        mock_handler.assert_called_once_with(payload, payload["actions"][0])


@pytest.mark.asyncio
async def test_schedule_background_task_logs_exception() -> None:
    async def _failing() -> None:
        raise RuntimeError("boom")

    _schedule_background_task(_failing(), name="test_fail")
    # Let the task run and the done callback fire
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    # Task should have been cleaned up from the set
    assert not any(t.get_name() == "test_fail" for t in _background_tasks)


@pytest.mark.asyncio
async def test_schedule_background_task_cleans_up_on_success() -> None:
    async def _ok() -> None:
        pass

    _schedule_background_task(_ok(), name="test_ok")
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not any(t.get_name() == "test_ok" for t in _background_tasks)
