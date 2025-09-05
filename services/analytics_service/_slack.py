import re
import threading
from datetime import datetime, timedelta

from fastapi.responses import JSONResponse, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy.orm import Session

from db.session import SyncSessionLocal
from services.analytics_service._implementation import get_reports
from services.analytics_service._utils import normalize_datetime_to_utc
from utils.log import logger
from utils.secret import get_client_secret_with_fallback

# =============================================================================
# DATE UTILITY FUNCTIONS
# =============================================================================


def parse_custom_date_range(message_text: str) -> tuple[datetime, datetime] | None:
    """
    Parse custom date range from message text like "from 2024-01-01 to 2024-01-31".
    Supports YYYY-MM-DD format with case-insensitive matching.

    Args:
        message_text: The full message text from Slack

    Returns:
        tuple[datetime, datetime] | None: (start_date, end_date) in UTC, or None if no match
    """
    # Pattern to match "from YYYY-MM-DD to YYYY-MM-DD" format (case insensitive)
    pattern = r"from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})"
    match = re.search(pattern, message_text, re.IGNORECASE)

    if not match:
        return None

    start_str = match.group(1).strip()
    end_str = match.group(2).strip()

    try:
        start_date = datetime.strptime(start_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_str, "%Y-%m-%d")
        start_date = normalize_datetime_to_utc(start_date)
        end_date = normalize_datetime_to_utc(end_date)

        return start_date, end_date

    except ValueError as e:
        logger.warning(
            f"[Slackbot] Failed to parse date range '{start_str}' to '{end_str}': {e}"
        )
        return None


def get_date_range_for_period(period: str) -> tuple[datetime, datetime]:
    """
    Generate start_date and end_date for different reporting periods.

    Args:
        period: "daily", "weekly", or "monthly"

    Returns:
        tuple[datetime, datetime]: (start_date, end_date) in UTC
    """
    now = datetime.utcnow()
    now = normalize_datetime_to_utc(now)

    if period == "daily":
        # Daily: yesterday this time to now (24-hour rolling window)
        start_date = now - timedelta(days=1)
        end_date = now

    elif period == "weekly":
        # Weekly: 7 days ago at 00:00 to today at 00:00 (clean week boundaries)
        start_date = (now - timedelta(days=7)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    elif period == "monthly":
        # Monthly: first day of previous month to first day of current month
        first_day_current = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        if now.month == 1:
            first_day_previous = first_day_current.replace(year=now.year - 1, month=12)
        else:
            first_day_previous = first_day_current.replace(month=now.month - 1)

        start_date = first_day_previous
        end_date = first_day_current

    else:
        raise ValueError(
            f"Unsupported period: {period}. Use 'daily', 'weekly', or 'monthly'"
        )

    # Normalize both dates to ensure they are timezone-aware UTC
    start_date = normalize_datetime_to_utc(start_date)
    end_date = normalize_datetime_to_utc(end_date)

    return start_date, end_date


# =============================================================================
# SLACK REPORTING FUNCTIONS
# =============================================================================


# Global column lists for different report sections
ENGAGEMENT_COLUMNS = [
    "active_users",
    "total_conversations",
    "total_turns",
    "avg_turns",
    "total_calls",
    "avg_duration",
    "transfer_calls",
    "transfer_rate",
    "positive_calls",
    "negative_calls",
]

CONVERSION_COLUMNS = [
    "conversations_with_orders",
    "paid_orders",
    "total_subtotal",
    "paid_total",
    "conversion_rate",
    "paid_rate",
]

ALL_COLUMNS = ENGAGEMENT_COLUMNS + CONVERSION_COLUMNS


def create_column_config(key: str, header: str, format_type: str = "int") -> dict:
    """Create a standardized column configuration."""
    format_funcs = {
        "int": lambda x: str(x) if x is not None else "N/A",
        "float": lambda x: f"{x:.1f}" if x is not None else "N/A",
        "percent": lambda x: f"{x:.1f}%" if x is not None else "N/A",
        "currency": lambda x: f"${x:.2f}" if x is not None else "N/A",
        "duration": lambda x: f"{x:.1f}s" if x is not None else "N/A",
    }

    return {
        "header": header,
        "data_key": key,
        "format_func": format_funcs.get(format_type, format_funcs["int"]),
    }


# Column configuration for unified reports
REPORT_COLUMNS = {
    # Engagement metrics
    "active_users": create_column_config("active_users", "Active Users"),
    "total_conversations": create_column_config("total_conversations", "Total Conv"),
    "total_turns": create_column_config("total_turns", "Total Turns"),
    "avg_turns": create_column_config("avg_turns", "Avg Turns", "float"),
    "total_calls": create_column_config("total_calls", "Total Calls"),
    "avg_duration": create_column_config("avg_duration", "Avg Duration", "duration"),
    "transfer_calls": create_column_config("transfer_calls", "Transfer Calls"),
    "transfer_rate": create_column_config("transfer_rate", "Transfer Rate", "percent"),
    "positive_calls": create_column_config("positive_calls", "Positive Calls"),
    "negative_calls": create_column_config("negative_calls", "Negative Calls"),
    # Conversion metrics
    "conversations_with_orders": create_column_config(
        "conversations_with_orders", "Conv w/ Orders"
    ),
    "paid_orders": create_column_config("paid_orders", "Paid Orders"),
    "total_subtotal": create_column_config(
        "total_subtotal", "Total Revenue", "currency"
    ),
    "paid_total": create_column_config("paid_total", "Paid Revenue", "currency"),
    "conversion_rate": create_column_config(
        "conversion_rate", "Conversion Rate", "percent"
    ),
    "paid_rate": create_column_config("paid_rate", "Paid Rate", "percent"),
}


def merge_report_data(reports: list) -> dict:
    """
    Merge multiple report types into unified account data structure.

    Args:
        reports: List of report objects with name and data attributes

    Returns:
        dict: Unified account data with all metrics
    """
    unified_accounts = {}
    totals_summary = {}

    # Process each report type
    for report in reports:
        report_name = report.name
        report_data = report.data

        # Extract totals for summary
        if "totals" in report_data:
            totals_summary[report_name] = report_data["totals"]

        # Extract account-level data
        account_data_key = None
        if report_name == "ACTIVE_USERS":
            account_data_key = "active_users"
        elif report_name == "MESSAGE_TURNS":
            account_data_key = "turn_distribution"
        elif report_name == "CALL_METRICS":
            account_data_key = "call_time_metrics"
        elif report_name == "CONVERSION_METRICS":
            account_data_key = "conversion_metrics"

        if account_data_key and account_data_key in report_data:
            accounts = report_data[account_data_key]

            for account_name, metrics in accounts.items():
                if account_name not in unified_accounts:
                    unified_accounts[account_name] = {}

                # Merge metrics into unified structure
                unified_accounts[account_name].update(metrics)

    return {"unified_accounts": unified_accounts, "totals_summary": totals_summary}


def create_slack_table_cell(text: str) -> dict:
    """Create a standardized Slack table cell."""
    return {
        "type": "rich_text",
        "elements": [
            {"type": "rich_text_section", "elements": [{"type": "text", "text": text}]}
        ],
    }


def create_slack_header_cell(text: str) -> dict:
    """Create a standardized Slack table header cell with bold styling."""
    return {
        "type": "rich_text",
        "elements": [
            {
                "type": "rich_text_section",
                "elements": [{"type": "text", "text": text, "style": {"bold": True}}],
            }
        ],
    }


def create_engagement_table(unified_accounts: dict, columns: list[str]) -> list:
    """Create engagement metrics table rows."""
    # Build table header
    header_row = [create_slack_header_cell("Account")]
    for col_key in columns:
        if col_key in REPORT_COLUMNS:
            header_row.append(
                create_slack_header_cell(REPORT_COLUMNS[col_key]["header"])
            )

    table_rows = [header_row]

    # Build data rows
    for account_name, account_data in unified_accounts.items():
        row = [create_slack_table_cell(account_name)]

        for col_key in columns:
            if col_key in REPORT_COLUMNS:
                col_config = REPORT_COLUMNS[col_key]
                value = account_data.get(col_config["data_key"])
                formatted_value = col_config["format_func"](value)
                row.append(create_slack_table_cell(formatted_value))

        table_rows.append(row)

    return table_rows


def create_conversion_table(unified_accounts: dict) -> list:
    """Create conversion metrics table rows, filtering out accounts with 0 orders."""
    # Filter out accounts with 0 conversations_with_orders
    filtered_accounts = {
        account_name: account_data
        for account_name, account_data in unified_accounts.items()
        if account_data.get("conversations_with_orders", 0) > 0
    }

    return create_engagement_table(filtered_accounts, CONVERSION_COLUMNS)


def format_unified_report_for_slack(
    reports: list, columns: list[str] | None = None
) -> dict:
    """
    Format unified analytics report into Slack blocks with configurable columns.

    Args:
        reports: List of report objects to merge
        columns: List of column keys to include (defaults to all available)

    Returns:
        dict: Slack blocks structure
    """
    try:
        # Use default columns if none specified
        if columns is None:
            columns = ENGAGEMENT_COLUMNS

        # Merge all report data
        merged_data = merge_report_data(reports)
        unified_accounts = merged_data["unified_accounts"]
        totals_summary = merged_data["totals_summary"]

        # Build summary section
        summary_lines = []
        if "ACTIVE_USERS" in totals_summary:
            total_users = totals_summary["ACTIVE_USERS"].get("total_active_users", 0)
            summary_lines.append(f"• Active Users: *{total_users}*")

        if "MESSAGE_TURNS" in totals_summary:
            total_convs = totals_summary["MESSAGE_TURNS"].get(
                "total_total_conversations", 0
            )
            avg_turns = totals_summary["MESSAGE_TURNS"].get(
                "avg_turns_per_conversation", 0
            )
            summary_lines.append(
                f"• Conversations: *{total_convs}* (Avg {avg_turns:.1f} turns)"
            )

        if "CALL_METRICS" in totals_summary:
            total_calls = totals_summary["CALL_METRICS"].get("total_total_calls", 0)
            avg_duration = totals_summary["CALL_METRICS"].get("avg_duration", 0)
            summary_lines.append(f"• Calls: *{total_calls}* (Avg {avg_duration:.1f}s)")

        summary_text = "*📊 Engagement Summary*\n" + "\n".join(summary_lines)

        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": summary_text}}]

        if not unified_accounts:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "No account data available."},
                }
            )
            return {"blocks": blocks}

        # Add engagement table
        engagement_table_rows = create_engagement_table(unified_accounts, columns)
        blocks.append({"type": "table", "rows": engagement_table_rows})

        # Add conversion summary section if conversion data exists
        has_conversion_data = "CONVERSION_METRICS" in totals_summary or any(
            any(
                key in account_data
                for key in [
                    "conversations_with_orders",
                    "paid_orders",
                    "total_subtotal",
                    "paid_total",
                    "conversion_rate",
                    "paid_rate",
                ]
            )
            for account_data in unified_accounts.values()
        )

        if has_conversion_data:
            # Build conversion summary
            conversion_summary_lines = []
            if "CONVERSION_METRICS" in totals_summary:
                conv_totals = totals_summary["CONVERSION_METRICS"]
                total_convs_with_orders = conv_totals.get(
                    "total_conversations_with_orders", 0
                )
                total_paid_orders = conv_totals.get("total_paid_orders", 0)
                total_revenue = conv_totals.get("total_subtotal", 0)
                paid_revenue = conv_totals.get("total_paid_total", 0)
                overall_conversion_rate = conv_totals.get("overall_conversion_rate", 0)
                overall_paid_rate = conv_totals.get("overall_paid_rate", 0)

                conversion_summary_lines.extend(
                    [
                        f"• Orders: *{total_convs_with_orders}* (Paid: *{total_paid_orders}*)",
                        f"• Revenue: *${total_revenue:.2f}* (Paid: *${paid_revenue:.2f}*)",
                        f"• Conversion Rate: *{overall_conversion_rate:.1f}%* | Paid Rate: *{overall_paid_rate:.1f}%*",
                    ]
                )

            conversion_summary_text = "*💰 Conversion Summary*\n" + "\n".join(
                conversion_summary_lines
            )

            blocks.extend(
                [
                    {"type": "divider"},
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": conversion_summary_text},
                    },
                ]
            )

            # Add conversion table
            conversion_table_rows = create_conversion_table(unified_accounts)
            blocks.append({"type": "table", "rows": conversion_table_rows})

        return {"blocks": blocks}

    except Exception as e:
        logger.error(f"Error formatting unified report for Slack: {e}")
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Error formatting report data: {str(e)}",
                    },
                }
            ]
        }


# Legacy function for backward compatibility
def format_active_users_for_slack(active_users_data: dict) -> dict:
    """Legacy function - use format_unified_report_for_slack instead."""

    # Convert single report to list format for unified function
    class MockReport:
        def __init__(self, name, data):
            self.name = name
            self.data = data

    reports = [MockReport("ACTIVE_USERS", active_users_data)]
    return format_unified_report_for_slack(reports, columns=["active_users"])


async def send_report_to_slack(
    slack_channel: str | None = None,
    client: AsyncWebClient | None = None,
    session: Session | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict:
    """
    Send a comprehensive engagement report to Slack with unified analytics.

    Args:
        slack_channel (str): Slack slack_channel to send to (optional, uses secret manager if not provided)
        client (AsyncWebClient): Optional async Slack client to reuse (creates new one if not provided)
        session (Session): Database session for fetching analytics data
        start_date (datetime): Start date for the report
        end_date (datetime): End date for the report

    Returns:
        dict: Status of the operation
    """
    try:
        # Get bot token from AWS Secrets Manager with environment variable fallback
        try:
            bot_token = get_client_secret_with_fallback("SLACK_BOT_TOKEN")
        except ValueError as e:
            logger.error(
                f"[Slackbot] SLACK_BOT_TOKEN not found in secrets manager or environment: {e}"
            )
            return {"status": "error", "message": "Slack bot token not configured"}

        # Get slack_channel from parameter or AWS Secrets Manager
        if not slack_channel:
            try:
                target_slack_channel = get_client_secret_with_fallback("SLACK_CHANNEL")
            except ValueError:
                target_slack_channel = "#test-channel"  # Default fallback
        else:
            target_slack_channel = slack_channel

        # Use provided client or create new one
        if client is None:
            client = AsyncWebClient(token=bot_token)

        # Get reports data
        if session is None:
            return {"status": "error", "message": "Database session not available"}

        reports = await get_reports(
            session, None, start_date, end_date, group_by=["account_id"]
        )

        if not reports.reports:
            return {"status": "error", "message": "No reports data available"}

        # Convert reports to Slack blocks format
        try:
            message_blocks = format_unified_report_for_slack(reports.reports)
            logger.info(
                f"[Slackbot] Successfully converted {len(reports.reports)} reports to Slack blocks"
            )

            # Validate blocks structure
            if not message_blocks or "blocks" not in message_blocks:
                return {"status": "error", "message": "Failed to generate Slack blocks"}

        except Exception as e:
            logger.error(f"[Slackbot] Error converting reports to Slack blocks: {e}")
            return {"status": "error", "message": f"Block conversion failed: {str(e)}"}

        # Send the message
        if client is None:
            return {"status": "error", "message": "Slack client not available"}

        response = await client.chat_postMessage(
            channel=target_slack_channel, text="Engagement Report", **message_blocks
        )

        if response["ok"]:
            logger.info(
                f"[Slackbot] Engagement report sent successfully to Slack channel {target_slack_channel}"
            )
            return {
                "status": "success",
                "message": f"Engagement report sent to Slack channel {target_slack_channel} successfully",
            }
        else:
            logger.error(
                f"[Slackbot] Failed to send to Slack: {response.get('error', 'Unknown error')}"
            )
            return {
                "status": "error",
                "message": f"Failed to send to Slack: {response.get('error', 'Unknown error')}",
            }

    except SlackApiError as e:
        logger.error(f"[Slackbot] Slack API error: {e.response['error']}")
        return {"status": "error", "message": f"Slack API error: {e.response['error']}"}
    except Exception as e:
        logger.error(f"[Slackbot] Error sending engagement report to Slack: {e}")
        return {"status": "error", "message": f"Failed to send report: {str(e)}"}


async def handle_report_request(
    period: str, message, client, custom_dates: tuple[datetime, datetime] | None = None
):
    """
    Generic handler for all report requests (daily, weekly, monthly, custom).

    Args:
        period: The report period ("daily", "weekly", "monthly", "custom")
        message: Slack message object
        client: Slack client object
        custom_dates: Optional tuple of (start_date, end_date) for custom ranges
    """
    try:
        slack_channel = message.get("channel")
        user = message["user"]

        logger.info(
            f"[Slackbot] User {user} requested {period} report in slack_channel {slack_channel}"
        )

        # Get date range - either custom or predefined period
        if custom_dates:
            start_date, end_date = custom_dates
            logger.info(
                f"[Slackbot] Using custom date range: {start_date} to {end_date}"
            )
        else:
            start_date, end_date = get_date_range_for_period(period)

        # Get database session for conversion data using proper context handling
        result = {"status": "error", "message": "No result"}

        session = SyncSessionLocal()
        try:
            result = await send_report_to_slack(
                slack_channel, client, session, start_date, end_date
            )
        finally:
            session.close()

        if result["status"] == "success":
            logger.info(
                f"[Slackbot] {period.capitalize()} report sent successfully to {slack_channel}"
            )
        else:
            logger.error(
                f"[Slackbot] Failed to send {period} report: {result['message']}"
            )

    except Exception as e:
        logger.error(f"[Slackbot] Error handling {period} request: {e}")


async def handle_custom_date_request(message, client):
    """
    Handle custom date range requests like "From 2024-01-01 to 2024-01-31".

    Args:
        message: Slack message object
        client: Slack client object
    """
    try:
        message_text = message.get("text", "")
        custom_dates = parse_custom_date_range(message_text)

        if custom_dates:
            await handle_report_request("custom", message, client, custom_dates)
        else:
            # Send help message if parsing failed
            slack_channel = message.get("channel")
            help_text = (
                "📅 *Custom Date Range Help*\n\n"
                "Please use the format: `From YYYY-MM-DD to YYYY-MM-DD`\n\n"
                "Example: `From 2024-01-01 to 2024-01-31`"
            )

            await client.chat_postMessage(
                channel=slack_channel, text=help_text, mrkdwn=True
            )

    except Exception as e:
        logger.error(f"[Slackbot] Error handling custom date request: {e}")


# =============================================================================
# SLACK APP CONFIGURATION
# =============================================================================


def create_slack_app():
    """Create and configure Slack Bolt app with event handlers."""
    try:
        # Get bot token and signing secret from AWS Secrets Manager with environment variable fallback
        bot_token = get_client_secret_with_fallback("SLACK_BOT_TOKEN")
        signing_secret = get_client_secret_with_fallback("SLACK_SIGNING_SECRET")
    except ValueError as e:
        logger.warning(
            f"[Slackbot] SLACK_BOT_TOKEN or SLACK_SIGNING_SECRET not found in secrets manager or environment: {e} - Slack event handling disabled"
        )
        return None

    app = AsyncApp(token=bot_token, signing_secret=signing_secret)

    @app.message("daily")
    async def handle_daily_request(message, client):
        """Handle when users send 'daily' in the slack_channel."""
        await handle_report_request("daily", message, client)

    @app.message("weekly")
    async def handle_weekly_request(message, client):
        """Handle when users send 'weekly' in the slack_channel."""
        await handle_report_request("weekly", message, client)

    @app.message("monthly")
    async def handle_monthly_request(message, client):
        """Handle when users send 'monthly' in the slack_channel."""
        await handle_report_request("monthly", message, client)

    @app.message(
        re.compile(r"from\s+\d{4}-\d{2}-\d{2}\s+to\s+\d{4}-\d{2}-\d{2}", re.IGNORECASE)
    )
    async def handle_custom_date_message(message, client):
        """Handle custom date range requests like 'From 2024-01-01 to 2024-01-31'."""
        await handle_custom_date_request(message, client)

    return app


# =============================================================================
# SLACK EVENT HANDLING
# =============================================================================


# Global Slack app instance and thread safety
_slack_app = None
_slack_handler = None
_slack_init_lock = threading.Lock()


async def handle_slack_events(request) -> Response:
    """
    Handle all Slack events by passing untouched request to Slack Bolt handler.
    This allows proper signature verification and URL verification by Slack Bolt.

    Args:
        request: FastAPI Request object (untouched - no request.json() called)

    Returns:
        FastAPI Response object from Slack Bolt handler
    """
    try:
        # Get Slack handler and let it handle everything (including URL verification)
        # Important: Don't call request.json() as it breaks Bolt's signature verification
        handler = _get_slack_handler()
        if handler:
            return await handler.handle(request)
        else:
            logger.error("[Slackbot] Slack handler not configured")
            return JSONResponse(
                status_code=503,
                content={"status": "error", "message": "Slack handler not configured"},
            )

    except Exception as e:
        logger.error(f"[Slackbot] Error handling Slack event: {e}")
        return JSONResponse(
            status_code=500, content={"status": "error", "message": str(e)}
        )


def _get_slack_handler():
    """Internal function to get the Slack request handler."""
    global _slack_app, _slack_handler

    if _slack_handler is None:
        with _slack_init_lock:
            # Double-check pattern to prevent race conditions
            if _slack_handler is None:
                _slack_app = create_slack_app()
                if _slack_app:
                    _slack_handler = AsyncSlackRequestHandler(_slack_app)

    return _slack_handler
