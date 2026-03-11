"""
Mercury Bot Interactive Action Handlers

Handles button clicks from the Mercury interactive help menu (block_actions)
and modal form submissions (view_submission) for Mercury workflows.

Dispatched from _interactions.py when action_id or callback_id starts with
'mercury_'. For direct-execution actions, commands run by constructing synthetic
event dicts and delegating to existing handlers in _commands.py.
"""

from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo

from services.slack_service._client import get_slack_client
from utils.log import logger

# Actions that execute directly without opening a modal (safe to background).
MERCURY_DIRECT_ACTIONS: frozenset[str] = frozenset(
    {
        "mercury_daily",
        "mercury_weekly",
        "mercury_monthly",
        "mercury_feedback_all",
        "mercury_camera_all",
    }
)

# =============================================================================
# BLOCK ACTIONS — Help menu button clicks
# =============================================================================


async def handle_mercury_block_action(
    payload: Dict[str, Any],
    action: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Handle Mercury help menu button clicks (block_actions).

    Routes to direct command execution or opens a modal based on the action_id.

    Args:
        payload: Full Slack interaction payload
        action: The specific action that was triggered

    Returns:
        dict: Success response for Slack
    """
    action_id = action.get("action_id", "")
    channel_id = payload.get("channel", {}).get("id", "")
    user_id = payload.get("user", {}).get("id", "")
    trigger_id = payload.get("trigger_id", "")

    logger.info(
        "[Mercury] Button clicked: %s",
        action_id,
        extra={
            "action_id": action_id,
            "channel_id": channel_id,
            "user_id": user_id,
        },
    )

    client = get_slack_client()

    # --- Direct command execution (no additional user input needed) ---

    if action_id in ("mercury_daily", "mercury_weekly", "mercury_monthly"):
        period = action_id.replace("mercury_", "")
        fake_event = {"channel": channel_id, "text": period, "user": user_id}
        from services.slack_service._commands import handle_report_request

        try:
            await handle_report_request(period, fake_event, client)
        except Exception as e:
            logger.error(
                "[Mercury] Error running %s report: %s",
                period,
                e,
                extra={"channel_id": channel_id, "user_id": user_id},
                exc_info=True,
            )
            await _notify_error(client, channel_id, "generating the report")
        return {"ok": True}

    if action_id == "mercury_feedback_all":
        fake_event = {"channel": channel_id, "text": "feedback", "user": user_id}
        from services.slack_service._commands import handle_feedback_request

        try:
            await handle_feedback_request(fake_event, client)
        except Exception as e:
            logger.error(
                "[Mercury] Error running feedback all: %s",
                e,
                extra={"channel_id": channel_id, "user_id": user_id},
                exc_info=True,
            )
            await _notify_error(client, channel_id, "looking up feedback")
        return {"ok": True}

    if action_id == "mercury_camera_all":
        fake_event = {"channel": channel_id, "text": "camera", "user": user_id}
        from services.slack_service._commands import handle_camera_request

        try:
            await handle_camera_request(fake_event, client)
        except Exception as e:
            logger.error(
                "[Mercury] Error running camera all: %s",
                e,
                extra={"channel_id": channel_id, "user_id": user_id},
                exc_info=True,
            )
            await _notify_error(client, channel_id, "checking camera status")
        return {"ok": True}

    # --- Modal openers (additional user input needed) ---

    try:
        if action_id == "mercury_custom_report":
            from services.slack_service._modals import build_report_modal

            await client.views_open(
                trigger_id=trigger_id, view=build_report_modal(channel_id)
            )
            return {"ok": True}

        if action_id == "mercury_feedback_lookup":
            from services.slack_service._modals import build_feedback_lookup_modal

            await client.views_open(
                trigger_id=trigger_id, view=build_feedback_lookup_modal(channel_id)
            )
            return {"ok": True}

        if action_id == "mercury_subscription":
            from services.slack_service._modals import build_subscription_lookup_modal

            await client.views_open(
                trigger_id=trigger_id,
                view=build_subscription_lookup_modal(channel_id),
            )
            return {"ok": True}

        if action_id == "mercury_camera_filter":
            from services.slack_service._modals import build_camera_filter_modal

            await client.views_open(
                trigger_id=trigger_id, view=build_camera_filter_modal(channel_id)
            )
            return {"ok": True}

        if action_id == "mercury_last_hours":
            from services.slack_service._modals import build_last_hours_modal

            await client.views_open(
                trigger_id=trigger_id, view=build_last_hours_modal(channel_id)
            )
            return {"ok": True}

        if action_id == "mercury_date_range":
            from services.slack_service._modals import build_date_range_modal

            await client.views_open(
                trigger_id=trigger_id, view=build_date_range_modal(channel_id)
            )
            return {"ok": True}

        if action_id == "mercury_tool_feedback":
            from services.notion_service import get_internal_tools
            from services.slack_service._modals import build_tool_feedback_modal

            tools = await get_internal_tools()
            await client.views_open(
                trigger_id=trigger_id,
                view=build_tool_feedback_modal(tools[:100], channel_id),
            )
            return {"ok": True}

        if action_id == "mercury_tool_request":
            from services.slack_service._modals import build_tool_request_modal

            await client.views_open(
                trigger_id=trigger_id, view=build_tool_request_modal(channel_id)
            )
            return {"ok": True}

    except Exception as e:
        logger.error(
            "[Mercury] Error opening modal for %s: %s",
            action_id,
            e,
            extra={"action_id": action_id, "channel_id": channel_id},
            exc_info=True,
        )
        await _notify_error(client, channel_id, "opening the form")
        return {"ok": True}

    logger.warning(
        "[Mercury] Unknown action_id: %s",
        action_id,
        extra={"action_id": action_id},
    )
    return {"ok": True}


# =============================================================================
# VIEW SUBMISSIONS — Modal form submissions
# =============================================================================


async def handle_mercury_view_submission(
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Handle Mercury modal form submissions (view_submission).

    Routes to the appropriate handler based on the modal's callback_id.

    Args:
        payload: Full Slack interaction payload

    Returns:
        dict: Success response for Slack (closes the modal)
    """
    view = payload.get("view", {})
    callback_id = view.get("callback_id", "")
    values = view.get("state", {}).get("values", {})
    channel_id = view.get("private_metadata", "")
    user_id = payload.get("user", {}).get("id", "")
    user_name = payload.get("user", {}).get("name", "")

    logger.info(
        "[Mercury] Modal submitted: %s",
        callback_id,
        extra={
            "callback_id": callback_id,
            "channel_id": channel_id,
            "user_id": user_id,
        },
    )

    if callback_id == "mercury_tool_feedback_submit":
        return await _handle_tool_feedback(values, channel_id, user_id, user_name)

    if callback_id == "mercury_report_submit":
        return await _handle_report(values, channel_id, user_id)

    if callback_id == "mercury_feedback_lookup_submit":
        return await _handle_feedback_lookup(values, channel_id, user_id)

    if callback_id == "mercury_subscription_submit":
        return await _handle_subscription(values, channel_id, user_id)

    if callback_id == "mercury_camera_filter_submit":
        return await _handle_camera_filter(values, channel_id, user_id)

    if callback_id == "mercury_last_hours_submit":
        return await _handle_last_hours(values, channel_id, user_id)

    if callback_id == "mercury_date_range_submit":
        return await _handle_date_range(values, channel_id, user_id)

    if callback_id == "mercury_tool_request_submit":
        return await _handle_tool_request(values, channel_id, user_id, user_name)

    logger.warning(
        "[Mercury] Unknown callback_id: %s",
        callback_id,
        extra={"callback_id": callback_id},
    )
    return {"ok": True}


# =============================================================================
# PRIVATE HANDLERS — Individual modal submission processors
# =============================================================================


async def _notify_error(client: Any, channel_id: str, action_desc: str) -> None:
    """Send an error notification to the user. Logs if notification itself fails."""
    if not channel_id:
        return
    try:
        await client.chat_postMessage(
            channel=channel_id,
            text=f":x: An error occurred while {action_desc}.",
        )
    except Exception as notify_err:
        logger.error(
            "[Mercury] Failed to send error notification: %s",
            notify_err,
            extra={"channel_id": channel_id},
        )


async def _handle_tool_feedback(
    values: dict,
    channel_id: str,
    user_id: str,
    user_name: str,
) -> Dict[str, Any]:
    """Handle tool feedback modal submission — creates a Notion feedback entry
    and posts a confirmation (or error) message to the originating channel."""
    client = get_slack_client()

    try:
        tool_value = values["tool_select"]["tool_name"]["selected_option"]["value"]
        tool_name = values["tool_select"]["tool_name"]["selected_option"]["text"][
            "text"
        ]

        # Parse combined value: "page_id|owner_id"
        if "|" in tool_value:
            tool_page_id, tool_owner_id = tool_value.split("|", 1)
        else:
            tool_page_id = tool_value
            tool_owner_id = ""

        if tool_page_id == "unknown":
            if channel_id:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=":warning: No tools are currently available. Please try again later.",
                )
            return {"ok": True}

        request_type = values["feedback_type"]["feedback_type_value"][
            "selected_option"
        ]["value"]
        priority = values["priority"]["priority_value"]["selected_option"]["value"]
        feedback_text = (
            values["feedback_text"]["feedback_content"]["value"] or ""
        ).strip()

        if not feedback_text:
            if channel_id:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=":warning: Please provide feedback details before submitting.",
                )
            return {"ok": True}

        from services.notion_service import submit_tool_feedback

        page_url = await submit_tool_feedback(
            tool_name=tool_name,
            tool_page_id=tool_page_id,
            request_type=request_type,
            priority=priority,
            feedback_text=feedback_text,
            submitted_by=user_name,
            submitted_by_id=user_id,
            tool_owner_id=tool_owner_id,
        )

        if page_url and channel_id:
            await client.chat_postMessage(
                channel=channel_id,
                text=f"Feedback submitted for {tool_name}",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f":white_check_mark: Feedback submitted for *{tool_name}*",
                        },
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": (
                                    f"*Type:* {request_type} · *Priority:* {priority} · "
                                    f"<{page_url}|View in Notion>"
                                ),
                            }
                        ],
                    },
                ],
            )
        elif channel_id:
            await client.chat_postMessage(
                channel=channel_id,
                text=":x: Failed to submit feedback. Please try again.",
            )

    except Exception as e:
        logger.error(
            "[Mercury] Error handling tool feedback submission: %s",
            e,
            extra={"user_id": user_id, "channel_id": channel_id},
            exc_info=True,
        )
        await _notify_error(client, channel_id, "submitting feedback")

    return {"ok": True}


async def _handle_report(
    values: dict,
    channel_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """Handle report modal submission — runs the selected report."""
    client = get_slack_client()

    try:
        period = values["report_period"]["period_value"]["selected_option"]["value"]
        account_input = values.get("account_name", {}).get("account_value", {})
        account_name = account_input.get("value", "").strip() if account_input else ""

        event = {"channel": channel_id, "text": period, "user": user_id}
        from services.slack_service._commands import handle_report_request

        await handle_report_request(
            period, event, client, account_name=account_name or None
        )

    except Exception as e:
        logger.error(
            "[Mercury] Error handling report submission: %s",
            e,
            extra={"user_id": user_id, "channel_id": channel_id},
            exc_info=True,
        )
        await _notify_error(client, channel_id, "generating the report")

    return {"ok": True}


async def _handle_feedback_lookup(
    values: dict,
    channel_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """Handle feedback lookup modal submission."""
    client = get_slack_client()

    try:
        client_name = values["client_name"]["client_value"]["value"].strip()
        lookup_type = values["lookup_type"]["lookup_value"]["selected_option"]["value"]

        if not client_name:
            if channel_id:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=":warning: Please provide a client name.",
                )
            return {"ok": True}

        fake_event = {
            "channel": channel_id,
            "text": f"{lookup_type} {client_name}",
            "user": user_id,
        }

        if lookup_type == "feedback-status":
            from services.slack_service._commands import handle_feedback_status_request

            await handle_feedback_status_request(fake_event, client)
        else:
            from services.slack_service._commands import handle_feedback_request

            await handle_feedback_request(fake_event, client)

    except Exception as e:
        logger.error(
            "[Mercury] Error handling feedback lookup: %s",
            e,
            extra={"user_id": user_id, "channel_id": channel_id},
            exc_info=True,
        )
        await _notify_error(client, channel_id, "looking up feedback")

    return {"ok": True}


async def _handle_subscription(
    values: dict,
    channel_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """Handle subscription lookup modal submission."""
    client = get_slack_client()

    try:
        account_name = values["account_name"]["account_value"]["value"].strip()

        if not account_name:
            if channel_id:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=":warning: Please provide an account name.",
                )
            return {"ok": True}

        fake_event = {
            "channel": channel_id,
            "text": f"subscription for {account_name}",
            "user": user_id,
        }

        from services.slack_service._commands import handle_subscription_request

        await handle_subscription_request(fake_event, client)

    except Exception as e:
        logger.error(
            "[Mercury] Error handling subscription lookup: %s",
            e,
            extra={"user_id": user_id, "channel_id": channel_id},
            exc_info=True,
        )
        await _notify_error(client, channel_id, "checking subscription")

    return {"ok": True}


async def _handle_camera_filter(
    values: dict,
    channel_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """Handle camera filter modal submission."""
    client = get_slack_client()

    try:
        accounts_input = values.get("account_names", {}).get("accounts_value", {})
        accounts_text = (
            accounts_input.get("value", "").strip() if accounts_input else ""
        )

        text = "camera"
        if accounts_text:
            text = f"camera for {accounts_text}"

        fake_event = {"channel": channel_id, "text": text, "user": user_id}

        from services.slack_service._commands import handle_camera_request

        await handle_camera_request(fake_event, client)

    except Exception as e:
        logger.error(
            "[Mercury] Error handling camera filter: %s",
            e,
            extra={"user_id": user_id, "channel_id": channel_id},
            exc_info=True,
        )
        await _notify_error(client, channel_id, "checking camera status")

    return {"ok": True}


async def _handle_last_hours(
    values: dict,
    channel_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """Handle last X hours modal submission — runs a report for the given window.

    Passes structured hours and account_name directly to the command handler,
    bypassing text serialization and regex parsing.
    """
    client = get_slack_client()

    try:
        hours_raw = values["hours"]["hours_value"]["value"].strip()

        if not hours_raw.isdigit() or int(hours_raw) <= 0:
            if channel_id:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=":warning: Please enter a valid number of hours (e.g. 6).",
                )
            return {"ok": True}

        hours = int(hours_raw)
        account_input = values.get("account_name", {}).get("account_value", {})
        account_name = account_input.get("value", "").strip() if account_input else ""

        event = {"channel": channel_id, "text": "", "user": user_id}
        from services.slack_service._commands import handle_last_hours_request

        await handle_last_hours_request(
            event,
            client,
            hours=hours,
            account_name=account_name or None,
        )

    except Exception as e:
        logger.error(
            "[Mercury] Error handling last hours submission: %s",
            e,
            extra={"user_id": user_id, "channel_id": channel_id},
            exc_info=True,
        )
        await _notify_error(client, channel_id, "generating the report")

    return {"ok": True}


async def _handle_date_range(
    values: dict,
    channel_id: str,
    user_id: str,
) -> Dict[str, Any]:
    """Handle date range modal submission — runs a report for the given date range.

    Parses dates from the datepicker and passes them directly as custom_dates,
    bypassing text serialization and regex parsing.
    """
    client = get_slack_client()

    try:
        start_str = values["start_date"]["start_date_value"]["selected_date"]
        end_str = values["end_date"]["end_date_value"]["selected_date"]

        if not start_str or not end_str:
            if channel_id:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=":warning: Please select both a start and end date.",
                )
            return {"ok": True}

        account_input = values.get("account_name", {}).get("account_value", {})
        account_name = account_input.get("value", "").strip() if account_input else ""

        pst = ZoneInfo("America/Los_Angeles")
        start_date = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=pst)
        end_date = datetime.strptime(end_str, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=pst
        )

        if end_date < start_date:
            if channel_id:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=":warning: End date must be on or after the start date.",
                )
            return {"ok": True}

        utc = ZoneInfo("UTC")
        start_utc = start_date.astimezone(utc)
        end_utc = end_date.astimezone(utc)

        event = {"channel": channel_id, "text": "", "user": user_id}
        from services.slack_service._commands import handle_report_request

        await handle_report_request(
            "custom",
            event,
            client,
            custom_dates=(start_utc, end_utc),
            account_name=account_name or None,
        )

    except Exception as e:
        logger.error(
            "[Mercury] Error handling date range submission: %s",
            e,
            extra={"user_id": user_id, "channel_id": channel_id},
            exc_info=True,
        )
        await _notify_error(client, channel_id, "generating the report")

    return {"ok": True}


async def _handle_tool_request(
    values: dict,
    channel_id: str,
    user_id: str,
    user_name: str,
) -> Dict[str, Any]:
    """Handle new tool request modal submission — creates a Notion tool request
    entry and posts a confirmation (or error) message to the originating channel."""
    client = get_slack_client()

    try:
        request_title = values["request_title"]["request_value"]["value"].strip()

        if not request_title:
            if channel_id:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=":warning: Please provide a request title.",
                )
            return {"ok": True}

        priority = values["priority"]["priority_value"]["selected_option"]["value"]

        problem_input = values.get("problem_context", {}).get("problem_value", {})
        problem_context = (
            problem_input.get("value", "").strip() if problem_input else ""
        )

        solution_input = values.get("proposed_solution", {}).get("solution_value", {})
        proposed_solution = (
            solution_input.get("value", "").strip() if solution_input else ""
        )

        from services.notion_service import submit_tool_request

        page_url = await submit_tool_request(
            request_title=request_title,
            priority=priority,
            problem_context=problem_context,
            proposed_solution=proposed_solution,
            submitted_by=user_name,
            submitted_by_id=user_id,
        )

        if page_url and channel_id:
            await client.chat_postMessage(
                channel=channel_id,
                text=f"Tool request submitted: {request_title}",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f":white_check_mark: Tool request submitted: *{request_title}*",
                        },
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": (
                                    f"*Priority:* {priority} · "
                                    f"<{page_url}|View in Notion>"
                                ),
                            }
                        ],
                    },
                ],
            )
        elif channel_id:
            await client.chat_postMessage(
                channel=channel_id,
                text=":x: Failed to submit tool request. Please try again.",
            )

    except Exception as e:
        logger.error(
            "[Mercury] Error handling tool request submission: %s",
            e,
            extra={"user_id": user_id, "channel_id": channel_id},
            exc_info=True,
        )
        await _notify_error(client, channel_id, "submitting the tool request")

    return {"ok": True}
