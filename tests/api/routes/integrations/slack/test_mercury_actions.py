"""Tests for Mercury bot interactive action handlers."""

from unittest.mock import AsyncMock, patch

import pytest

from api.routes.integrations.slack._mercury_actions import (
    _notify_error,
    handle_mercury_block_action,
    handle_mercury_view_submission,
)


def _make_payload(
    action_id: str = "",
    channel_id: str = "C123",
    user_id: str = "U123",
    trigger_id: str = "T123",
) -> tuple[dict, dict]:
    """Create a minimal Slack interaction payload and action."""
    payload = {
        "channel": {"id": channel_id},
        "user": {"id": user_id, "name": "testuser"},
        "trigger_id": trigger_id,
    }
    action = {"action_id": action_id, "value": action_id}
    return payload, action


def _make_view_payload(
    callback_id: str,
    values: dict,
    channel_id: str = "C123",
    user_id: str = "U123",
) -> dict:
    """Create a minimal Slack view_submission payload."""
    return {
        "view": {
            "callback_id": callback_id,
            "state": {"values": values},
            "private_metadata": channel_id,
        },
        "user": {"id": user_id, "name": "testuser"},
    }


class TestNotifyError:
    @pytest.mark.asyncio
    async def test_sends_error_message(self) -> None:
        mock_client = AsyncMock()
        await _notify_error(mock_client, "C123", "doing something")
        mock_client.chat_postMessage.assert_called_once()
        assert (
            "doing something" in mock_client.chat_postMessage.call_args.kwargs["text"]
        )

    @pytest.mark.asyncio
    async def test_skips_when_no_channel(self) -> None:
        mock_client = AsyncMock()
        await _notify_error(mock_client, "", "doing something")
        mock_client.chat_postMessage.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_when_notification_fails(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat_postMessage.side_effect = Exception("Slack down")
        # Should not raise
        await _notify_error(mock_client, "C123", "doing something")


class TestHandleMercuryBlockAction:
    @pytest.mark.asyncio
    async def test_daily_report_calls_handler(self) -> None:
        payload, action = _make_payload("mercury_daily")
        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_report_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_handler.assert_called_once()
            call_args = mock_handler.call_args[0]
            assert call_args[0] == "daily"

    @pytest.mark.asyncio
    async def test_weekly_report_calls_handler(self) -> None:
        payload, action = _make_payload("mercury_weekly")
        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_report_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_handler.assert_called_once()
            call_args = mock_handler.call_args[0]
            assert call_args[0] == "weekly"

    @pytest.mark.asyncio
    async def test_feedback_all_calls_handler(self) -> None:
        payload, action = _make_payload("mercury_feedback_all")
        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_feedback_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_camera_all_calls_handler(self) -> None:
        payload, action = _make_payload("mercury_camera_all")
        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_camera_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_direct_command_error_sends_notification(self) -> None:
        payload, action = _make_payload("mercury_daily")
        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_report_request",
                new_callable=AsyncMock,
                side_effect=Exception("Report failed"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()
            assert "error" in mock_client.chat_postMessage.call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_custom_report_opens_modal(self) -> None:
        payload, action = _make_payload("mercury_custom_report")
        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.views_open.assert_called_once()
            view = mock_client.views_open.call_args.kwargs["view"]
            assert view["callback_id"] == "mercury_report_submit"

    @pytest.mark.asyncio
    async def test_tool_feedback_fetches_tools_and_opens_modal(self) -> None:
        payload, action = _make_payload("mercury_tool_feedback")
        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.notion_service.get_internal_tools",
                new_callable=AsyncMock,
                return_value=[{"name": "Tool A", "page_id": "id1"}],
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.views_open.assert_called_once()
            view = mock_client.views_open.call_args.kwargs["view"]
            assert view["callback_id"] == "mercury_tool_feedback_submit"

    @pytest.mark.asyncio
    async def test_tool_request_opens_modal(self) -> None:
        payload, action = _make_payload("mercury_tool_request")
        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.views_open.assert_called_once()
            view = mock_client.views_open.call_args.kwargs["view"]
            assert view["callback_id"] == "mercury_tool_request_submit"

    @pytest.mark.asyncio
    async def test_modal_open_error_sends_notification(self) -> None:
        payload, action = _make_payload("mercury_custom_report")
        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_client.views_open.side_effect = Exception("Slack API error")
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_feedback_all_error_sends_notification(self) -> None:
        payload, action = _make_payload("mercury_feedback_all")
        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_feedback_request",
                new_callable=AsyncMock,
                side_effect=Exception("Feedback failed"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_camera_all_error_sends_notification(self) -> None:
        payload, action = _make_payload("mercury_camera_all")
        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_camera_request",
                new_callable=AsyncMock,
                side_effect=Exception("Camera failed"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_feedback_lookup_opens_modal(self) -> None:
        payload, action = _make_payload("mercury_feedback_lookup")
        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.views_open.assert_called_once()
            view = mock_client.views_open.call_args.kwargs["view"]
            assert view["callback_id"] == "mercury_feedback_lookup_submit"

    @pytest.mark.asyncio
    async def test_subscription_opens_modal(self) -> None:
        payload, action = _make_payload("mercury_subscription")
        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.views_open.assert_called_once()
            view = mock_client.views_open.call_args.kwargs["view"]
            assert view["callback_id"] == "mercury_subscription_submit"

    @pytest.mark.asyncio
    async def test_camera_filter_opens_modal(self) -> None:
        payload, action = _make_payload("mercury_camera_filter")
        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.views_open.assert_called_once()
            view = mock_client.views_open.call_args.kwargs["view"]
            assert view["callback_id"] == "mercury_camera_filter_submit"

    @pytest.mark.asyncio
    async def test_monthly_report_calls_handler(self) -> None:
        payload, action = _make_payload("mercury_monthly")
        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_report_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_handler.assert_called_once()
            call_args = mock_handler.call_args[0]
            assert call_args[0] == "monthly"

    @pytest.mark.asyncio
    async def test_last_hours_opens_modal(self) -> None:
        payload, action = _make_payload("mercury_last_hours")
        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.views_open.assert_called_once()
            view = mock_client.views_open.call_args.kwargs["view"]
            assert view["callback_id"] == "mercury_last_hours_submit"

    @pytest.mark.asyncio
    async def test_date_range_opens_modal(self) -> None:
        payload, action = _make_payload("mercury_date_range")
        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_block_action(payload, action)

            assert result == {"ok": True}
            mock_client.views_open.assert_called_once()
            view = mock_client.views_open.call_args.kwargs["view"]
            assert view["callback_id"] == "mercury_date_range_submit"

    @pytest.mark.asyncio
    async def test_unknown_action_returns_ok(self) -> None:
        payload, action = _make_payload("mercury_unknown_action")
        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_block_action(payload, action)
            assert result == {"ok": True}


class TestHandleMercuryViewSubmission:
    @pytest.mark.asyncio
    async def test_tool_feedback_submit_creates_notion_page(self) -> None:
        values = {
            "tool_select": {
                "tool_name": {
                    "selected_option": {
                        "value": "page-id-123|owner-456",
                        "text": {"text": "Analytics"},
                    }
                }
            },
            "feedback_type": {
                "feedback_type_value": {"selected_option": {"value": "Bug"}}
            },
            "priority": {"priority_value": {"selected_option": {"value": "P1"}}},
            "feedback_text": {"feedback_content": {"value": "Something is broken"}},
        }
        payload = _make_view_payload("mercury_tool_feedback_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.notion_service.submit_tool_feedback",
                new_callable=AsyncMock,
                return_value="https://notion.so/page",
            ) as mock_submit,
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_submit.assert_called_once_with(
                tool_name="Analytics",
                tool_page_id="page-id-123",
                request_type="Bug",
                priority="P1",
                feedback_text="Something is broken",
                submitted_by="testuser",
                submitted_by_id="U123",
                tool_owner_id="owner-456",
            )
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_request_submit_creates_notion_page(self) -> None:
        values = {
            "request_title": {"request_value": {"value": "New Dashboard Tool"}},
            "priority": {"priority_value": {"selected_option": {"value": "P2"}}},
            "problem_context": {
                "problem_value": {"value": "We need better visibility"}
            },
            "proposed_solution": {
                "solution_value": {"value": "Build a Grafana dashboard"}
            },
        }
        payload = _make_view_payload("mercury_tool_request_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.notion_service.submit_tool_request",
                new_callable=AsyncMock,
                return_value="https://notion.so/request",
            ) as mock_submit,
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_submit.assert_called_once_with(
                request_title="New Dashboard Tool",
                priority="P2",
                problem_context="We need better visibility",
                proposed_solution="Build a Grafana dashboard",
                submitted_by="testuser",
                submitted_by_id="U123",
            )
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_request_submit_with_empty_optional_fields(self) -> None:
        values = {
            "request_title": {"request_value": {"value": "Simple Request"}},
            "priority": {"priority_value": {"selected_option": {"value": "P3"}}},
        }
        payload = _make_view_payload("mercury_tool_request_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.notion_service.submit_tool_request",
                new_callable=AsyncMock,
                return_value="https://notion.so/request",
            ) as mock_submit,
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_submit.assert_called_once()
            call_kwargs = mock_submit.call_args.kwargs
            assert call_kwargs["problem_context"] == ""
            assert call_kwargs["proposed_solution"] == ""

    @pytest.mark.asyncio
    async def test_tool_request_submit_posts_error_on_failure(self) -> None:
        values = {
            "request_title": {"request_value": {"value": "Failing Request"}},
            "priority": {"priority_value": {"selected_option": {"value": "P1"}}},
        }
        payload = _make_view_payload("mercury_tool_request_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.notion_service.submit_tool_request",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            call_args = mock_client.chat_postMessage.call_args
            assert "Failed" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_report_submit_calls_report_handler(self) -> None:
        values = {
            "report_period": {"period_value": {"selected_option": {"value": "daily"}}},
            "account_name": {"account_value": {"value": "romeo"}},
        }
        payload = _make_view_payload("mercury_report_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_report_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_feedback_submit_exception_sends_notification(self) -> None:
        values = {
            "tool_select": {
                "tool_name": {
                    "selected_option": {
                        "value": "page-id-123",
                        "text": {"text": "Analytics"},
                    }
                }
            },
            "feedback_type": {
                "feedback_type_value": {"selected_option": {"value": "Bug"}}
            },
            "priority": {"priority_value": {"selected_option": {"value": "P1"}}},
            "feedback_text": {"feedback_content": {"value": "Something is broken"}},
        }
        payload = _make_view_payload("mercury_tool_feedback_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.notion_service.submit_tool_feedback",
                new_callable=AsyncMock,
                side_effect=Exception("Notion down"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_feedback_submit_returns_none_posts_error(self) -> None:
        values = {
            "tool_select": {
                "tool_name": {
                    "selected_option": {
                        "value": "page-id-123",
                        "text": {"text": "Analytics"},
                    }
                }
            },
            "feedback_type": {
                "feedback_type_value": {"selected_option": {"value": "Bug"}}
            },
            "priority": {"priority_value": {"selected_option": {"value": "P1"}}},
            "feedback_text": {"feedback_content": {"value": "Something is broken"}},
        }
        payload = _make_view_payload("mercury_tool_feedback_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.notion_service.submit_tool_feedback",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            call_args = mock_client.chat_postMessage.call_args
            assert "Failed" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_report_submit_error_sends_notification(self) -> None:
        values = {
            "report_period": {"period_value": {"selected_option": {"value": "daily"}}},
        }
        payload = _make_view_payload("mercury_report_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_report_request",
                new_callable=AsyncMock,
                side_effect=Exception("Report failed"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_report_submit_with_account_name(self) -> None:
        values = {
            "report_period": {"period_value": {"selected_option": {"value": "weekly"}}},
            "account_name": {"account_value": {"value": "acme"}},
        }
        payload = _make_view_payload("mercury_report_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_report_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_feedback_lookup_submit_open_issues(self) -> None:
        values = {
            "client_name": {"client_value": {"value": "romeo"}},
            "lookup_type": {"lookup_value": {"selected_option": {"value": "feedback"}}},
        }
        payload = _make_view_payload("mercury_feedback_lookup_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_feedback_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_feedback_lookup_submit_full_history(self) -> None:
        values = {
            "client_name": {"client_value": {"value": "romeo"}},
            "lookup_type": {
                "lookup_value": {"selected_option": {"value": "feedback-status"}}
            },
        }
        payload = _make_view_payload("mercury_feedback_lookup_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_feedback_status_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_feedback_lookup_submit_error_sends_notification(self) -> None:
        values = {
            "client_name": {"client_value": {"value": "romeo"}},
            "lookup_type": {"lookup_value": {"selected_option": {"value": "feedback"}}},
        }
        payload = _make_view_payload("mercury_feedback_lookup_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_feedback_request",
                new_callable=AsyncMock,
                side_effect=Exception("Lookup failed"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscription_submit_calls_handler(self) -> None:
        values = {
            "account_name": {"account_value": {"value": "romeo"}},
        }
        payload = _make_view_payload("mercury_subscription_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_subscription_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_subscription_submit_error_sends_notification(self) -> None:
        values = {
            "account_name": {"account_value": {"value": "romeo"}},
        }
        payload = _make_view_payload("mercury_subscription_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_subscription_request",
                new_callable=AsyncMock,
                side_effect=Exception("Sub failed"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_camera_filter_submit_calls_handler(self) -> None:
        values = {
            "account_names": {"accounts_value": {"value": "romeo,juliet"}},
        }
        payload = _make_view_payload("mercury_camera_filter_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_camera_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_camera_filter_submit_empty_accounts(self) -> None:
        values = {}
        payload = _make_view_payload("mercury_camera_filter_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_camera_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_camera_filter_submit_error_sends_notification(self) -> None:
        values = {
            "account_names": {"accounts_value": {"value": "romeo"}},
        }
        payload = _make_view_payload("mercury_camera_filter_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_camera_request",
                new_callable=AsyncMock,
                side_effect=Exception("Camera failed"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_request_submit_exception_sends_notification(self) -> None:
        values = {
            "request_title": {"request_value": {"value": "New Tool"}},
            "priority": {"priority_value": {"selected_option": {"value": "P1"}}},
        }
        payload = _make_view_payload("mercury_tool_request_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.notion_service.submit_tool_request",
                new_callable=AsyncMock,
                side_effect=Exception("Notion down"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_feedback_lookup_empty_client_name_posts_warning(self) -> None:
        values = {
            "client_name": {"client_value": {"value": "  "}},
            "lookup_type": {"lookup_value": {"selected_option": {"value": "feedback"}}},
        }
        payload = _make_view_payload("mercury_feedback_lookup_submit", values)

        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()
            assert (
                "client name" in mock_client.chat_postMessage.call_args.kwargs["text"]
            )

    @pytest.mark.asyncio
    async def test_subscription_empty_account_posts_warning(self) -> None:
        values = {
            "account_name": {"account_value": {"value": "  "}},
        }
        payload = _make_view_payload("mercury_subscription_submit", values)

        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()
            assert (
                "account name" in mock_client.chat_postMessage.call_args.kwargs["text"]
            )

    @pytest.mark.asyncio
    async def test_tool_feedback_unknown_tool_posts_warning(self) -> None:
        values = {
            "tool_select": {
                "tool_name": {
                    "selected_option": {
                        "value": "unknown",
                        "text": {"text": "(No tools found)"},
                    }
                }
            },
            "feedback_type": {
                "feedback_type_value": {"selected_option": {"value": "Bug"}}
            },
            "priority": {"priority_value": {"selected_option": {"value": "P1"}}},
            "feedback_text": {"feedback_content": {"value": "test"}},
        }
        payload = _make_view_payload("mercury_tool_feedback_submit", values)

        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()
            assert "No tools" in mock_client.chat_postMessage.call_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_tool_request_empty_title_posts_warning(self) -> None:
        values = {
            "request_title": {"request_value": {"value": "   "}},
            "priority": {"priority_value": {"selected_option": {"value": "P1"}}},
        }
        payload = _make_view_payload("mercury_tool_request_submit", values)

        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()
            assert (
                "request title" in mock_client.chat_postMessage.call_args.kwargs["text"]
            )

    @pytest.mark.asyncio
    async def test_last_hours_submit_calls_handler(self) -> None:
        values = {
            "hours": {"hours_value": {"value": "6"}},
            "account_name": {"account_value": {"value": "romeo"}},
        }
        payload = _make_view_payload("mercury_last_hours_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_last_hours_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_handler.assert_called_once()
            call_kwargs = mock_handler.call_args.kwargs
            assert call_kwargs["hours"] == 6
            assert call_kwargs["account_name"] == "romeo"

    @pytest.mark.asyncio
    async def test_last_hours_submit_invalid_hours_posts_warning(self) -> None:
        values = {
            "hours": {"hours_value": {"value": "abc"}},
        }
        payload = _make_view_payload("mercury_last_hours_submit", values)

        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()
            assert (
                "valid number" in mock_client.chat_postMessage.call_args.kwargs["text"]
            )

    @pytest.mark.asyncio
    async def test_last_hours_submit_error_sends_notification(self) -> None:
        values = {
            "hours": {"hours_value": {"value": "6"}},
        }
        payload = _make_view_payload("mercury_last_hours_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_last_hours_request",
                new_callable=AsyncMock,
                side_effect=Exception("Report failed"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_date_range_submit_calls_handler(self) -> None:
        values = {
            "start_date": {"start_date_value": {"selected_date": "2024-01-01"}},
            "end_date": {"end_date_value": {"selected_date": "2024-01-31"}},
            "account_name": {"account_value": {"value": "acme"}},
        }
        payload = _make_view_payload("mercury_date_range_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_report_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_handler.assert_called_once()
            call_kwargs = mock_handler.call_args.kwargs
            assert call_kwargs["account_name"] == "acme"
            start, end = call_kwargs["custom_dates"]
            # Dates are converted from PST to UTC
            assert str(start.tzinfo) == "UTC"
            assert start.strftime("%Y-%m-%d %H:%M") == "2024-01-01 08:00"
            assert end.strftime("%Y-%m-%d %H:%M") == "2024-02-01 07:59"

    @pytest.mark.asyncio
    async def test_date_range_submit_without_account(self) -> None:
        values = {
            "start_date": {"start_date_value": {"selected_date": "2024-06-01"}},
            "end_date": {"end_date_value": {"selected_date": "2024-06-30"}},
        }
        payload = _make_view_payload("mercury_date_range_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_report_request",
                new_callable=AsyncMock,
            ) as mock_handler,
        ):
            mock_get_client.return_value = AsyncMock()
            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_handler.assert_called_once()
            call_kwargs = mock_handler.call_args.kwargs
            assert call_kwargs["account_name"] is None

    @pytest.mark.asyncio
    async def test_date_range_submit_error_sends_notification(self) -> None:
        values = {
            "start_date": {"start_date_value": {"selected_date": "2024-01-01"}},
            "end_date": {"end_date_value": {"selected_date": "2024-01-31"}},
        }
        payload = _make_view_payload("mercury_date_range_submit", values)

        with (
            patch(
                "api.routes.integrations.slack._mercury_actions.get_slack_client"
            ) as mock_get_client,
            patch(
                "services.slack_service._commands.handle_report_request",
                new_callable=AsyncMock,
                side_effect=Exception("Date range failed"),
            ),
        ):
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()

    @pytest.mark.asyncio
    async def test_date_range_submit_end_before_start_posts_warning(self) -> None:
        values = {
            "start_date": {"start_date_value": {"selected_date": "2024-06-30"}},
            "end_date": {"end_date_value": {"selected_date": "2024-06-01"}},
        }
        payload = _make_view_payload("mercury_date_range_submit", values)

        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()
            msg = mock_client.chat_postMessage.call_args.kwargs["text"]
            assert "End date" in msg

    @pytest.mark.asyncio
    async def test_tool_feedback_submit_empty_text_posts_warning(self) -> None:
        values = {
            "tool_select": {
                "tool_name": {
                    "selected_option": {
                        "value": "page-id-123",
                        "text": {"text": "Analytics"},
                    }
                }
            },
            "feedback_type": {
                "feedback_type_value": {"selected_option": {"value": "Bug"}}
            },
            "priority": {"priority_value": {"selected_option": {"value": "P1"}}},
            "feedback_text": {"feedback_content": {"value": "   "}},
        }
        payload = _make_view_payload("mercury_tool_feedback_submit", values)

        with patch(
            "api.routes.integrations.slack._mercury_actions.get_slack_client"
        ) as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            result = await handle_mercury_view_submission(payload)

            assert result == {"ok": True}
            mock_client.chat_postMessage.assert_called_once()
            msg = mock_client.chat_postMessage.call_args.kwargs["text"]
            assert "feedback details" in msg

    @pytest.mark.asyncio
    async def test_unknown_callback_returns_ok(self) -> None:
        payload = _make_view_payload("mercury_unknown_callback", {})
        result = await handle_mercury_view_submission(payload)
        assert result == {"ok": True}
