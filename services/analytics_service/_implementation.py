import asyncio
import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

import db
from api.schemas.admin.analytics import (
    AnalyticsReportType,
    GetAllReportsResponse,
    PerformanceReport,
)
from api.schemas.admin.ordering_metrics import (
    OrderingMetricPoint,
    OrderingMetricsResponse,
    OrderingMetricSummary,
)
from api.schemas.admin.ordering_revenue_metrics import (
    OrderingRevenueAmountBucket,
    OrderingRevenueFulfillment,
    OrderingRevenueFulfillmentBucket,
    OrderingRevenueMetricsResponse,
    OrderingRevenuePaymentPath,
    OrderingRevenueStore,
    OrderingRevenueSummary,
    OrderingRevenueTimeSeriesPoint,
)
from services.analytics_service.schema import (
    CallInsightMetricAvailability,
    CallInsightRecord,
    CallInsightsResponse,
    CallInsightSummary,
)
from services.message_service._store_status import compute_store_status
from utils.log import logger

from ._utils import (
    CALL_QUALITY_METADATA_BY_VALUE,
    TRANSFER_REASON_METADATA_BY_KEY,
    _enforce_hierarchy_order,
    process_analytics_data_generic,
    validate_date_range,
)


async def get_reports(
    session: Session,
    account_id: uuid.UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> GetAllReportsResponse:
    """
    Get all analytics reports for a given account within a date range.
    This is the main analytics function that does all the heavy lifting.

    Args:
        session (Session): Database session
        account_id (uuid.UUID) | None: The account ID to calculate analytics for
        start_date (datetime | None): Start date for the calculation. If None, defaults to 7 days ago
        end_date (datetime | None): End date for the calculation. If None, defaults to today
        group_by (list[str] | None): List of fields to group by
        filter_by (dict): Filter parameters

    Returns:
        GetAllReportsResponse: Object containing all analytics reports
    """
    try:
        # Validate the date range
        start_date, end_date = validate_date_range(start_date, end_date)

        # Ensure account filtering is applied
        if filter_by is None:
            filter_by = {}
        if account_id:
            filter_by["account_id"] = account_id

        # Create a function that creates a new sync session for each thread operation
        def create_sync_session_and_run(func, **kwargs):
            from db.session import SyncSessionLocal

            sync_session = SyncSessionLocal()
            try:
                return func(session=sync_session, **kwargs)
            finally:
                sync_session.close()

        # Execute all analytics queries in parallel with separate sessions for each thread
        logger.info(
            f"Analytics: Starting parallel report execution for account {account_id}"
        )

        (
            users_report,
            turns_report,
            calls_report,
            call_info_report,
            conversion_report,
            transfer_reason_report,
            call_quality_report,
        ) = await asyncio.gather(
            asyncio.to_thread(
                create_sync_session_and_run,
                get_active_users,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
            asyncio.to_thread(
                create_sync_session_and_run,
                get_turns_summary,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
            asyncio.to_thread(
                create_sync_session_and_run,
                get_calls_time_summary,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
            asyncio.to_thread(
                create_sync_session_and_run,
                get_calls_info_summary,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
            asyncio.to_thread(
                create_sync_session_and_run,
                get_conversion_summary,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
            asyncio.to_thread(
                create_sync_session_and_run,
                get_transfer_reason_distribution,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
            asyncio.to_thread(
                create_sync_session_and_run,
                get_call_quality_distribution,
                start_date=start_date,
                end_date=end_date,
                group_by=group_by,
                filter_by=filter_by,
            ),
        )

        # Create and return reports
        reports = [
            PerformanceReport(
                name=AnalyticsReportType.ACTIVE_USERS.name, data=users_report
            ),
            PerformanceReport(
                name=AnalyticsReportType.MESSAGE_TURNS.name, data=turns_report
            ),
            PerformanceReport(
                name=AnalyticsReportType.CALL_METRICS.name, data=calls_report
            ),
            PerformanceReport(
                name=AnalyticsReportType.CALL_INFO_DISTRIBUTION.name,
                data=call_info_report,
            ),
            PerformanceReport(
                name=AnalyticsReportType.CONVERSION_METRICS.name,
                data=conversion_report,
            ),
            PerformanceReport(
                name=AnalyticsReportType.TRANSFER_REASON_DISTRIBUTION.name,
                data=transfer_reason_report,
            ),
            PerformanceReport(
                name=AnalyticsReportType.CALL_QUALITY_DISTRIBUTION.name,
                data=call_quality_report,
            ),
        ]

        return GetAllReportsResponse(reports=reports)

    except ValueError:
        return GetAllReportsResponse(reports=[])
    except Exception:
        logger.exception("Full analytics exception traceback:")
        return GetAllReportsResponse(reports=[])


async def get_account_reports(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> GetAllReportsResponse:
    """
    Wrapper function that calls get_reports for backward compatibility.

    Args:
        session (Session): Database session
        account_id (uuid.UUID): The account ID to calculate analytics for
        start_date (datetime | None): Start date for the calculation
        end_date (datetime | None): End date for the calculation
        group_by (list[str] | None): List of fields to group by
        filter_by (dict): Filter parameters

    Returns:
        GetAllReportsResponse: Object containing all analytics reports
    """
    return await get_reports(
        session=session,
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        group_by=group_by,
        filter_by=filter_by,
    )


def _to_date_key(value: date | datetime | str) -> str:
    """Return YYYY-MM-DD for DB date values."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value.split("T")[0]


def _calculate_accuracy(
    accurate_order_call_count: int, order_call_count: int
) -> float | None:
    """Calculate order accuracy percentage, or None when there is no denominator."""
    if order_call_count == 0:
        return None
    return round((accurate_order_call_count / order_call_count) * 100, 1)


def _empty_ordering_summary() -> OrderingMetricSummary:
    """Build an all-zero ordering summary."""
    return OrderingMetricSummary(
        total_orders=0,
        total_order_value=0.0,
        order_accuracy=None,
        order_call_count=0,
        accurate_order_call_count=0,
        tool_error_order_call_count=0,
    )


def _empty_revenue_amount_bucket() -> OrderingRevenueAmountBucket:
    return OrderingRevenueAmountBucket(orders=0, revenue=0.0)


def _empty_revenue_fulfillment_bucket() -> OrderingRevenueFulfillmentBucket:
    return OrderingRevenueFulfillmentBucket(orders=0, revenue=0.0, share=None)


def _empty_ordering_revenue_response(
    account_name: str,
    ordering_enabled: bool,
    period_start: str,
    period_end: str,
) -> OrderingRevenueMetricsResponse:
    return OrderingRevenueMetricsResponse(
        account_name=account_name,
        ordering_enabled=ordering_enabled,
        period_start=period_start,
        period_end=period_end,
        summary=OrderingRevenueSummary(
            total_orders=0,
            palona_revenue=0.0,
            palona_aov=0.0,
        ),
        time_series=[],
        payment_path=OrderingRevenuePaymentPath(
            payment_link=_empty_revenue_amount_bucket(),
            pay_in_store=_empty_revenue_amount_bucket(),
        ),
        fulfillment=OrderingRevenueFulfillment(
            takeout=_empty_revenue_fulfillment_bucket(),
            delivery=_empty_revenue_fulfillment_bucket(),
        ),
        stores=[],
    )


def _iter_date_keys(start_date: datetime, end_date: datetime) -> list[str]:
    """Return inclusive YYYY-MM-DD date keys for a datetime range."""
    current = start_date.date()
    end = end_date.date()
    dates: list[str] = []
    while current <= end:
        dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _build_ordering_filter_by(
    account_id: uuid.UUID, project_ids: list[uuid.UUID] | None
) -> dict[str, uuid.UUID | list[uuid.UUID]]:
    """Build analytics filters matching the Slack conversion metrics path."""
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] = {"account_id": account_id}
    if project_ids:
        filter_by["project_id"] = project_ids
    return filter_by


_CONVERSION_CONVERSATIONS_WITH_ORDERS_INDEX = 2
_CONVERSION_TOTAL_SUBTOTAL_INDEX = 4


_CALL_INSIGHT_AVAILABILITY = {
    "individual_call_duration": CallInsightMetricAvailability(
        available=True,
        source="phone_calls.duration",
    ),
    "after_hours_calls": CallInsightMetricAvailability(
        available=True,
        source="projects.business_hours/store_hours + projects.timezone",
        note="Null per call when project hours are missing or unparseable.",
    ),
    "spam_calls": CallInsightMetricAvailability(
        available=False,
        note="No persisted spam classification was found.",
    ),
    "internal_test_calls": CallInsightMetricAvailability(
        available=True,
        source="conversations.is_test",
    ),
    "new_repeat_callers": CallInsightMetricAvailability(
        available=True,
        source="users plus prior phone_calls for the same user",
    ),
    "transfer_requested_destination_reason": CallInsightMetricAvailability(
        available=True,
        source="conversations.transfer_purpose, phone_calls.transfer_reason_category, contacts/projects transfer destination",
    ),
    "concurrent_calls": CallInsightMetricAvailability(
        available=True,
        source="phone_calls.created_at + phone_calls.duration overlap within selected rows",
    ),
    "transfer_requested_at": CallInsightMetricAvailability(
        available=True,
        source="tool_call_records.created_at where tool_name contains call_transfer",
        note="Null when the transfer was inferred from ended_reason but no tool-call record exists.",
    ),
    "transferred_call_answered": CallInsightMetricAvailability(
        available=False,
        note="No downstream transferred-leg answer status was found.",
    ),
}


def _calculate_percentage(numerator: int, denominator: int) -> float | None:
    """Calculate a percentage with one decimal place, or None with no denominator."""
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100, 1)


def _to_int(value: object) -> int:
    """Convert SQL aggregate values to int for JSON report output."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (float, Decimal)):
        return int(value)
    return int(str(value))


def _to_float(value: object) -> float:
    """Convert SQL aggregate values to float for JSON report output."""
    if value is None:
        return 0.0
    if isinstance(value, (float, int, Decimal)):
        return float(value)
    return float(str(value))


def _to_revenue_aov(total_value: float, total_orders: int) -> float:
    return round(total_value / total_orders, 2) if total_orders > 0 else 0.0


def _to_palona_revenue_order_count(values: dict[str, int | float]) -> int:
    return int(values["payment_link_orders"]) + int(values["pay_in_store_orders"])


def _revenue_metric_values(row: dict[str, object]) -> dict[str, int | float]:
    return {
        "total_orders": _to_int(row["total_orders"]),
        "total_order_value": _to_float(row["total_order_value"]),
        "palona_revenue": _to_float(row["palona_revenue"]),
        "payment_link_orders": _to_int(row["payment_link_orders"]),
        "payment_link_revenue": _to_float(row["payment_link_revenue"]),
        "pay_in_store_orders": _to_int(row["pay_in_store_orders"]),
        "pay_in_store_revenue": _to_float(row["pay_in_store_revenue"]),
        "takeout_orders": _to_int(row["takeout_orders"]),
        "takeout_revenue": _to_float(row["takeout_revenue"]),
        "delivery_orders": _to_int(row["delivery_orders"]),
        "delivery_revenue": _to_float(row["delivery_revenue"]),
    }


def _to_group_date_key(value: object) -> str:
    """Convert a grouped SQL date value to the report date key format."""
    if isinstance(value, (date, datetime, str)):
        return _to_date_key(value)
    return str(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _calculate_after_hours(
    started_at: datetime,
    business_hours: dict | None,
    store_hours: str | None,
    timezone_name: str | None,
) -> bool | None:
    status = compute_store_status(
        business_hours=business_hours,
        store_hours_text=store_hours,
        timezone_str=timezone_name,
        now=_as_utc(started_at),
    )
    if status.get("status") == "hours_unknown":
        return None
    return not bool(status.get("is_open"))


def _has_concurrent_call(
    current_index: int,
    call_windows: Sequence[tuple[uuid.UUID | None, datetime, datetime | None]],
) -> bool:
    project_id, started_at, ended_at = call_windows[current_index]
    if project_id is None or ended_at is None:
        return False
    for other_index, (other_project_id, other_started_at, other_ended_at) in enumerate(
        call_windows
    ):
        if other_index == current_index or other_ended_at is None:
            continue
        if other_project_id is None or project_id != other_project_id:
            continue
        if other_started_at < ended_at and other_ended_at > started_at:
            return True
    return False


def _format_unknown_transfer_reason_label(reason: str) -> str:
    """Format unknown transfer reason keys defensively for report output."""
    return " ".join(word.capitalize() for word in reason.split("_") if word) or reason


def _call_quality_label_value(value: object) -> str:
    """Normalize SQLAlchemy enum or string call-quality labels."""
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def _is_legitimate_call_quality_label(label: str) -> bool:
    """Return whether a call-quality label represents a legitimate call."""
    metadata = CALL_QUALITY_METADATA_BY_VALUE.get(label)
    return metadata.is_legitimate if metadata else False


def _format_unknown_call_quality_label(label: str) -> str:
    """Format unknown call-quality labels defensively for report output."""
    return " ".join(word.capitalize() for word in label.split("_") if word) or label


def _parse_call_quality_row(
    row: tuple[object, ...],
    group_by: list[str],
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Parse a call-quality tuple into a report row and group identity."""
    index = 0
    report_row: dict[str, object] = {}
    group_key_parts: list[str] = []

    for group in group_by:
        if group == "date":
            date_key = _to_group_date_key(row[index])
            report_row["date"] = date_key
            group_key_parts.append(date_key)
            index += 1
        elif group == "account_id":
            account_id = str(row[index])
            account_name = str(row[index + 1])
            report_row["account_id"] = account_id
            report_row["account_name"] = account_name
            group_key_parts.append(account_id)
            index += 2
        elif group == "project_id":
            project_id = str(row[index])
            project_name = str(row[index + 1])
            report_row["project_id"] = project_id
            report_row["project_name"] = project_name
            group_key_parts.append(project_id)
            index += 2

    label = _call_quality_label_value(row[index])
    count = _to_int(row[index + 1])
    label_metadata = CALL_QUALITY_METADATA_BY_VALUE.get(label)

    report_row.update(
        {
            "call_quality_label": label,
            "label": (
                label_metadata.label
                if label_metadata
                else _format_unknown_call_quality_label(label)
            ),
            "description": (
                label_metadata.description
                if label_metadata
                else "Custom call quality label"
            ),
            "count": count,
            "is_legitimate": _is_legitimate_call_quality_label(label),
        }
    )

    return report_row, tuple(group_key_parts)


def _build_call_quality_rows(
    data: list[tuple[object, ...]],
    group_by: list[str],
) -> list[dict[str, object]]:
    """Build call-quality rows with percentages within each group."""
    parsed_rows: list[tuple[dict[str, object], tuple[str, ...]]] = []
    group_totals: dict[tuple[str, ...], int] = {}

    for row in data:
        report_row, group_key = _parse_call_quality_row(row, group_by)
        count = _to_int(report_row["count"])
        group_totals[group_key] = group_totals.get(group_key, 0) + count
        parsed_rows.append((report_row, group_key))

    output_rows: list[dict[str, object]] = []
    for report_row, group_key in parsed_rows:
        count = _to_int(report_row["count"])
        report_row["percentage"] = _calculate_percentage(
            count,
            group_totals.get(group_key, 0),
        )
        output_rows.append(report_row)

    output_rows.sort(
        key=lambda report_row: (
            tuple(str(report_row.get(group, "")) for group in group_by),
            -_to_int(report_row["count"]),
            str(report_row["call_quality_label"]),
        )
    )
    return output_rows


def _build_call_quality_totals(
    rows: list[dict[str, object]],
) -> dict[str, object]:
    """Build summary totals from ungrouped call-quality rows."""
    total_count = sum(_to_int(row["count"]) for row in rows)
    legitimate_count = sum(
        _to_int(row["count"]) for row in rows if bool(row["is_legitimate"])
    )
    non_legitimate_count = total_count - legitimate_count

    return {
        "total_call_quality_calls": total_count,
        "total_legitimate_calls": legitimate_count,
        "total_non_legitimate_calls": non_legitimate_count,
        "legitimate_rate": _calculate_percentage(legitimate_count, total_count),
        "non_legitimate_rate": _calculate_percentage(
            non_legitimate_count,
            total_count,
        ),
    }


def _parse_transfer_reason_row(
    row: tuple[object, ...],
    group_by: list[str],
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Parse a transfer reason tuple into a report row and group identity."""
    index = 0
    report_row: dict[str, object] = {}
    group_key_parts: list[str] = []

    for group in group_by:
        if group == "date":
            date_key = _to_group_date_key(row[index])
            report_row["date"] = date_key
            group_key_parts.append(date_key)
            index += 1
        elif group == "account_id":
            account_id = str(row[index])
            account_name = str(row[index + 1])
            report_row["account_id"] = account_id
            report_row["account_name"] = account_name
            group_key_parts.append(account_id)
            index += 2
        elif group == "project_id":
            project_id = str(row[index])
            project_name = str(row[index + 1])
            report_row["project_id"] = project_id
            report_row["project_name"] = project_name
            group_key_parts.append(project_id)
            index += 2

    reason = str(row[index])
    count = _to_int(row[index + 1])
    agent_fault_count = _to_int(row[index + 2])
    reason_metadata = TRANSFER_REASON_METADATA_BY_KEY.get(reason)

    report_row.update(
        {
            "reason": reason,
            "transfer_reason_category": reason,
            "label": (
                reason_metadata.label
                if reason_metadata
                else _format_unknown_transfer_reason_label(reason)
            ),
            "description": (
                reason_metadata.description
                if reason_metadata
                else "Custom transfer reason"
            ),
            "count": count,
            "agent_fault_count": agent_fault_count,
            "agent_fault_rate": _calculate_percentage(agent_fault_count, count),
        }
    )

    return report_row, tuple(group_key_parts)


def _build_transfer_reason_rows(
    data: list[tuple[object, ...]],
    group_by: list[str],
) -> list[dict[str, object]]:
    """Build transfer reason ranking rows with percentages within each group."""
    parsed_rows: list[tuple[dict[str, object], tuple[str, ...]]] = []
    group_totals: dict[tuple[str, ...], int] = {}

    for row in data:
        report_row, group_key = _parse_transfer_reason_row(row, group_by)
        count = _to_int(report_row["count"])
        group_totals[group_key] = group_totals.get(group_key, 0) + count
        parsed_rows.append((report_row, group_key))

    output_rows: list[dict[str, object]] = []
    for report_row, group_key in parsed_rows:
        count = _to_int(report_row["count"])
        report_row["percentage"] = _calculate_percentage(
            count,
            group_totals.get(group_key, 0),
        )
        output_rows.append(report_row)

    output_rows.sort(
        key=lambda report_row: (
            tuple(str(report_row.get(group, "")) for group in group_by),
            -_to_int(report_row["count"]),
            str(report_row["reason"]),
        )
    )
    return output_rows


def _build_transfer_reason_totals(
    rows: list[dict[str, object]],
) -> dict[str, object]:
    """Build summary totals from ungrouped transfer reason ranking rows."""
    total_count = sum(_to_int(row["count"]) for row in rows)
    agent_fault_count = sum(_to_int(row["agent_fault_count"]) for row in rows)

    return {
        "total_transfer_reason_calls": total_count,
        "agent_fault_calls": agent_fault_count,
        "agent_fault_rate": _calculate_percentage(agent_fault_count, total_count),
    }


async def get_ordering_metrics(
    session: Session,
    account_id: uuid.UUID,
    account_name: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    project_ids: list[uuid.UUID] | None = None,
) -> OrderingMetricsResponse:
    """
    Get ordering dashboard metrics and whether ordering is enabled.

    The capability gate is scoped to the selected projects when project_ids are
    provided. When enabled, the response includes a continuous daily series.
    """
    start_date, end_date = validate_date_range(start_date, end_date)
    analytics_repo = db.AnalyticsRepository(session)

    ordering_enabled = analytics_repo.has_ordering_enabled(
        account_id=account_id,
        project_ids=project_ids,
    )
    period_start = start_date.date().isoformat()
    period_end = end_date.date().isoformat()

    if not ordering_enabled:
        return OrderingMetricsResponse(
            account_name=account_name,
            ordering_enabled=False,
            period_start=period_start,
            period_end=period_end,
            time_series=[],
            summary=_empty_ordering_summary(),
        )

    conversion_rows = analytics_repo.get_conversion_summary(
        start_date=start_date,
        end_date=end_date,
        group_by=["date"],
        filter_by=_build_ordering_filter_by(account_id, project_ids),
    )
    accuracy_rows = analytics_repo.get_order_accuracy_time_series(
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        project_ids=project_ids,
    )

    conversion_rows_by_date: dict[str, tuple[int, float]] = {}
    for row in conversion_rows:
        row_date = row[0]
        date_key = _to_date_key(row_date)
        # get_conversion_summary(["date"]) matches Slack's ordering report shape.
        conversion_rows_by_date[date_key] = (
            int(row[_CONVERSION_CONVERSATIONS_WITH_ORDERS_INDEX] or 0),
            float(row[_CONVERSION_TOTAL_SUBTOTAL_INDEX] or Decimal("0")),
        )

    accurate_calls_by_date: dict[str, int] = {}
    for row_date, _order_calls, accurate_calls in accuracy_rows:
        date_key = _to_date_key(row_date)
        accurate_calls_by_date[date_key] = int(accurate_calls or 0)

    total_orders_summary = 0
    total_order_value_summary = 0.0
    order_call_count_summary = 0
    accurate_order_call_count_summary = 0
    time_series: list[OrderingMetricPoint] = []

    for date_key in _iter_date_keys(start_date, end_date):
        total_orders, total_order_value = conversion_rows_by_date.get(
            date_key, (0, 0.0)
        )
        order_calls = total_orders
        accurate_calls = accurate_calls_by_date.get(date_key, 0)
        tool_error_calls = order_calls - accurate_calls
        total_orders_summary += total_orders
        total_order_value_summary += total_order_value
        order_call_count_summary += order_calls
        accurate_order_call_count_summary += accurate_calls

        time_series.append(
            OrderingMetricPoint(
                date=date_key,
                total_orders=total_orders,
                total_order_value=round(total_order_value, 2),
                order_accuracy=_calculate_accuracy(accurate_calls, order_calls),
                order_call_count=order_calls,
                accurate_order_call_count=accurate_calls,
                tool_error_order_call_count=tool_error_calls,
            )
        )

    tool_error_order_call_count_summary = (
        order_call_count_summary - accurate_order_call_count_summary
    )

    return OrderingMetricsResponse(
        account_name=account_name,
        ordering_enabled=True,
        period_start=period_start,
        period_end=period_end,
        time_series=time_series,
        summary=OrderingMetricSummary(
            total_orders=total_orders_summary,
            total_order_value=round(total_order_value_summary, 2),
            order_accuracy=_calculate_accuracy(
                accurate_order_call_count_summary,
                order_call_count_summary,
            ),
            order_call_count=order_call_count_summary,
            accurate_order_call_count=accurate_order_call_count_summary,
            tool_error_order_call_count=tool_error_order_call_count_summary,
        ),
    )


def get_call_insights(
    session: Session,
    account_id: uuid.UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    project_ids: list[uuid.UUID] | None = None,
) -> CallInsightsResponse:
    """Get call-level business review metrics for an account."""
    start_date, end_date = validate_date_range(start_date, end_date)
    analytics_repo = db.AnalyticsRepository(session)
    rows = analytics_repo.get_call_insights(
        start_date=start_date,
        end_date=end_date,
        filter_by=_build_ordering_filter_by(account_id, project_ids),
    )

    call_windows: list[tuple[uuid.UUID | None, datetime, datetime | None]] = []
    for row in rows:
        started_at = _as_utc(row[2])
        duration = row[3]
        ended_at = (
            started_at + timedelta(seconds=float(duration))
            if duration is not None
            else None
        )
        call_windows.append((row[12], started_at, ended_at))

    records: list[CallInsightRecord] = []
    for index, row in enumerate(rows):
        (
            call_id,
            conversation_id,
            started_at,
            duration,
            ended_reason,
            transfer_reason_category,
            is_test,
            transfer_purpose,
            _user_id,
            caller_identifiers,
            account_row_id,
            account_name,
            project_id,
            project_name,
            timezone_name,
            business_hours,
            store_hours,
            transfer_destination,
            transfer_requested_at,
            prior_call_count,
        ) = row
        ended_reason_value = getattr(ended_reason, "value", ended_reason)
        is_transfer_requested = bool(
            transfer_purpose
            or transfer_reason_category
            or transfer_requested_at
            or ended_reason_value == "assistant_forwarded"
        )
        normalized_transfer_requested_at = (
            _as_utc(transfer_requested_at)
            if is_transfer_requested and transfer_requested_at
            else None
        )
        is_after_hours = _calculate_after_hours(
            started_at=started_at,
            business_hours=business_hours,
            store_hours=store_hours,
            timezone_name=timezone_name,
        )

        records.append(
            CallInsightRecord(
                call_id=str(call_id),
                conversation_id=conversation_id,
                account_id=account_row_id,
                account_name=str(account_name),
                project_id=project_id,
                project_name=project_name,
                caller_identifiers=list(caller_identifiers or []),
                started_at=_as_utc(started_at),
                duration_seconds=(
                    round(float(duration), 2) if duration is not None else None
                ),
                is_after_hours=is_after_hours,
                is_spam=None,
                is_internal_test=bool(is_test),
                is_new_caller=int(prior_call_count or 0) == 0,
                is_repeat_caller=int(prior_call_count or 0) > 0,
                transfer_requested=is_transfer_requested,
                transfer_destination=(
                    transfer_destination if is_transfer_requested else None
                ),
                transfer_reason=(
                    (transfer_reason_category or transfer_purpose)
                    if is_transfer_requested
                    else None
                ),
                transfer_requested_at=normalized_transfer_requested_at,
                transferred_call_answered=None,
                has_concurrent_call=_has_concurrent_call(index, call_windows),
            )
        )

    durations = [
        record.duration_seconds
        for record in records
        if record.duration_seconds is not None
    ]
    after_hours_values = [
        record.is_after_hours for record in records if record.is_after_hours is not None
    ]
    summary = CallInsightSummary(
        total_calls=len(records),
        avg_duration_seconds=(
            round(sum(durations) / len(durations), 2) if durations else None
        ),
        after_hours_calls=sum(1 for value in after_hours_values if value),
        spam_calls=None,
        internal_test_calls=sum(1 for record in records if record.is_internal_test),
        new_callers=sum(1 for record in records if record.is_new_caller),
        repeat_callers=sum(1 for record in records if record.is_repeat_caller),
        transfer_requested_calls=sum(
            1 for record in records if record.transfer_requested
        ),
        concurrent_calls=sum(1 for record in records if record.has_concurrent_call),
        transfer_answered_calls=None,
    )

    if not after_hours_values:
        summary.after_hours_calls = None

    return CallInsightsResponse(
        period_start=start_date,
        period_end=end_date,
        summary=summary,
        metric_availability=_CALL_INSIGHT_AVAILABILITY,
        calls=records,
    )


async def get_ordering_revenue_metrics(
    session: Session,
    account_id: uuid.UUID,
    account_name: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    project_ids: list[uuid.UUID] | None = None,
) -> OrderingRevenueMetricsResponse:
    """
    Get revenue dashboard metrics for Palona-created orders.

    Payment path is inferred from paid orders with provider-specific payment
    link evidence; pay_in_store is paid without that evidence.
    """
    start_date, end_date = validate_date_range(start_date, end_date)
    analytics_repo = db.AnalyticsRepository(session)

    ordering_enabled = analytics_repo.has_ordering_enabled(
        account_id=account_id,
        project_ids=project_ids,
    )
    period_start = start_date.date().isoformat()
    period_end = end_date.date().isoformat()

    if not ordering_enabled:
        return _empty_ordering_revenue_response(
            account_name=account_name,
            ordering_enabled=False,
            period_start=period_start,
            period_end=period_end,
        )

    filter_by = _build_ordering_filter_by(account_id, project_ids)
    daily_rows = analytics_repo.get_ordering_revenue_metrics(
        start_date=start_date,
        end_date=end_date,
        group_by="date",
        filter_by=filter_by,
    )
    daily_values_by_date: dict[str, dict[str, int | float]] = {}
    for row in daily_rows:
        daily_values_by_date[_to_group_date_key(row["date"])] = _revenue_metric_values(
            row
        )

    summary_values: dict[str, int | float] = {
        "total_orders": 0,
        "total_order_value": 0.0,
        "palona_revenue": 0.0,
        "payment_link_orders": 0,
        "payment_link_revenue": 0.0,
        "pay_in_store_orders": 0,
        "pay_in_store_revenue": 0.0,
        "takeout_orders": 0,
        "takeout_revenue": 0.0,
        "delivery_orders": 0,
        "delivery_revenue": 0.0,
    }
    for values in daily_values_by_date.values():
        for key, value in values.items():
            summary_values[key] += value

    total_orders = int(summary_values["total_orders"])
    palona_revenue_order_count = _to_palona_revenue_order_count(summary_values)

    time_series = []
    for date_key in _iter_date_keys(start_date, end_date):
        values = daily_values_by_date.get(date_key)
        if values is None:
            time_series.append(
                OrderingRevenueTimeSeriesPoint(
                    date=date_key,
                    total_orders=0,
                    palona_revenue=0.0,
                    palona_aov=0.0,
                    payment_link_orders=0,
                    payment_link_revenue=0.0,
                    pay_in_store_orders=0,
                    pay_in_store_revenue=0.0,
                    takeout_orders=0,
                    delivery_orders=0,
                )
            )
            continue

        day_orders = int(values["total_orders"])
        day_palona_revenue = float(values["palona_revenue"])
        day_palona_revenue_order_count = _to_palona_revenue_order_count(values)
        time_series.append(
            OrderingRevenueTimeSeriesPoint(
                date=date_key,
                total_orders=day_orders,
                palona_revenue=round(day_palona_revenue, 2),
                palona_aov=_to_revenue_aov(
                    day_palona_revenue, day_palona_revenue_order_count
                ),
                payment_link_orders=int(values["payment_link_orders"]),
                payment_link_revenue=round(float(values["payment_link_revenue"]), 2),
                pay_in_store_orders=int(values["pay_in_store_orders"]),
                pay_in_store_revenue=round(float(values["pay_in_store_revenue"]), 2),
                takeout_orders=int(values["takeout_orders"]),
                delivery_orders=int(values["delivery_orders"]),
            )
        )

    store_rows = analytics_repo.get_ordering_revenue_metrics(
        start_date=start_date,
        end_date=end_date,
        group_by="store",
        filter_by=filter_by,
    )
    stores: list[OrderingRevenueStore] = []
    for row in store_rows:
        store_id = str(row["store_id"]) if row["store_id"] is not None else None
        project_id = str(row["project_id"]) if row["project_id"] is not None else None
        project_name = (
            str(row["project_name"]) if row["project_name"] is not None else None
        )
        values = _revenue_metric_values(row)
        store_orders = int(values["total_orders"])
        store_palona_revenue = float(values["palona_revenue"])
        store_palona_revenue_order_count = _to_palona_revenue_order_count(values)
        stores.append(
            OrderingRevenueStore(
                store_id=store_id,
                store_name=project_name or store_id or "Unknown store",
                project_id=project_id,
                project_name=project_name,
                orders=store_orders,
                palona_revenue=round(store_palona_revenue, 2),
                palona_aov=_to_revenue_aov(
                    store_palona_revenue, store_palona_revenue_order_count
                ),
                payment_link=OrderingRevenueAmountBucket(
                    orders=int(values["payment_link_orders"]),
                    revenue=round(float(values["payment_link_revenue"]), 2),
                ),
                pay_in_store=OrderingRevenueAmountBucket(
                    orders=int(values["pay_in_store_orders"]),
                    revenue=round(float(values["pay_in_store_revenue"]), 2),
                ),
            )
        )

    return OrderingRevenueMetricsResponse(
        account_name=account_name,
        ordering_enabled=True,
        period_start=period_start,
        period_end=period_end,
        summary=OrderingRevenueSummary(
            total_orders=total_orders,
            palona_revenue=round(float(summary_values["palona_revenue"]), 2),
            palona_aov=_to_revenue_aov(
                float(summary_values["palona_revenue"]), palona_revenue_order_count
            ),
        ),
        time_series=time_series,
        payment_path=OrderingRevenuePaymentPath(
            payment_link=OrderingRevenueAmountBucket(
                orders=int(summary_values["payment_link_orders"]),
                revenue=round(float(summary_values["payment_link_revenue"]), 2),
            ),
            pay_in_store=OrderingRevenueAmountBucket(
                orders=int(summary_values["pay_in_store_orders"]),
                revenue=round(float(summary_values["pay_in_store_revenue"]), 2),
            ),
        ),
        fulfillment=OrderingRevenueFulfillment(
            takeout=OrderingRevenueFulfillmentBucket(
                orders=int(summary_values["takeout_orders"]),
                revenue=round(float(summary_values["takeout_revenue"]), 2),
                share=_calculate_percentage(
                    int(summary_values["takeout_orders"]), total_orders
                ),
            ),
            delivery=OrderingRevenueFulfillmentBucket(
                orders=int(summary_values["delivery_orders"]),
                revenue=round(float(summary_values["delivery_revenue"]), 2),
                share=_calculate_percentage(
                    int(summary_values["delivery_orders"]), total_orders
                ),
            ),
        ),
        stores=stores,
    )


def get_transfer_reason_distribution(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict[str, object]:
    """
    Get transfer reason ranking with agent-fault attribution.

    Returns:
        dict: {
            'transfer_reason_distribution': [...],
            'totals': {
                'transfer_reason_distribution': [...],
                'total_transfer_reason_calls': int,
                'agent_fault_calls': int,
                'agent_fault_rate': float | None
            },
            'metadata': {...}
        }
    """
    try:
        if group_by is None:
            group_by = []

        ordered_group_by = _enforce_hierarchy_order(group_by)
        analytics_repo = db.AnalyticsRepository(session)

        if ordered_group_by:
            transfer_reason_data, transfer_reason_totals_data = (
                analytics_repo.get_transfer_reason_distribution(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_transfer_reason_distribution(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],
                    filter_by=filter_by,
                ),
            )
        else:
            transfer_reason_data = []
            transfer_reason_totals_data = (
                analytics_repo.get_transfer_reason_distribution(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],
                    filter_by=filter_by,
                )
            )

        transfer_reason_rows = _build_transfer_reason_rows(
            transfer_reason_data,
            ordered_group_by,
        )
        total_rows = _build_transfer_reason_rows(transfer_reason_totals_data, [])
        totals = _build_transfer_reason_totals(total_rows)

        return {
            "transfer_reason_distribution": transfer_reason_rows,
            "totals": {
                **totals,
                "transfer_reason_distribution": total_rows,
            },
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

    except Exception as e:
        logger.error(f"Error generating transfer reason distribution: {e}")
        raise


def get_call_quality_distribution(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict[str, object]:
    """
    Get post-call quality classifier label counts.

    Returns:
        dict: {
            'call_quality_distribution': [...],
            'totals': {
                'call_quality_distribution': [...],
                'total_call_quality_calls': int,
                'total_legitimate_calls': int,
                'total_non_legitimate_calls': int,
                'legitimate_rate': float | None,
                'non_legitimate_rate': float | None
            },
            'metadata': {...}
        }
    """
    try:
        if group_by is None:
            group_by = []

        ordered_group_by = _enforce_hierarchy_order(group_by)
        analytics_repo = db.AnalyticsRepository(session)

        if ordered_group_by:
            call_quality_data, call_quality_totals_data = (
                analytics_repo.get_call_quality_distribution(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_call_quality_distribution(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],
                    filter_by=filter_by,
                ),
            )
        else:
            call_quality_data = analytics_repo.get_call_quality_distribution(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )
            call_quality_totals_data = call_quality_data

        call_quality_rows = _build_call_quality_rows(
            call_quality_data,
            ordered_group_by,
        )
        total_rows = _build_call_quality_rows(call_quality_totals_data, [])
        totals = _build_call_quality_totals(total_rows)

        return {
            "call_quality_distribution": call_quality_rows,
            "totals": {
                **totals,
                "call_quality_distribution": total_rows,
            },
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

    except Exception as e:
        logger.error(f"Error generating call quality distribution: {e}")
        raise


def get_active_users(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict:
    """
    Get active users analytics with flexible grouping and filtering.

    Args:
        session: Database session
        start_date: Start date for analysis
        end_date: End date for analysis
        group_by: List of fields to group by ['account_id', 'project_id'] (date is automatically prepended)
        filter_by: Dict of filters {'account_id': uuid|list[uuid], 'project_id': uuid|list[uuid]}

    Returns:
        dict: {
            'active_users': {...},
            'totals': {...},
            'metadata': {...}
        }
    """
    try:
        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Get both grouped and total data in parallel to reduce database calls
        if ordered_group_by:
            # If grouping is requested, get both grouped and total data
            active_users_data, active_users_totals_data = (
                analytics_repo.get_active_users(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_active_users(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],  # No grouping for accurate totals
                    filter_by=filter_by,
                ),
            )
        else:
            # If no grouping, only get totals (avoid duplicate query)
            active_users_data = []
            active_users_totals_data = analytics_repo.get_active_users(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )

        # Process Active Users Data using generic architecture
        active_users_report = process_analytics_data_generic(
            active_users_data,
            ordered_group_by,
            AnalyticsReportType.ACTIVE_USERS.metrics_config,
        )

        # Calculate totals from ungrouped data (accurate totals)
        totals = process_analytics_data_generic(
            active_users_totals_data,
            None,
            AnalyticsReportType.ACTIVE_USERS.metrics_config,
            calculate_totals=True,
        )

        result = {
            "active_users": active_users_report,
            "totals": totals,
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

        return result

    except Exception as e:
        logger.error(f"Error generating active users report: {e}")
        raise


def get_turns_summary(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict:
    """
    Get conversation turns summary with flexible grouping and filtering.

    Args:
        session: Database session
        start_date: Start date for analysis
        end_date: End date for analysis
        group_by: List of fields to group by ['account_id', 'project_id'] (date is automatically prepended)
        filter_by: Dict of filters {'account_id': uuid|list[uuid], 'project_id': uuid|list[uuid]}

    Returns:
        dict: {
            'turn_distribution': {...},
            'totals': {...},
            'metadata': {...}
        }
    """
    try:
        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Optimize database calls based on grouping requirements
        if ordered_group_by:
            # If grouping is requested, get both grouped and total data
            turn_distribution_data, turn_totals_data = (
                analytics_repo.get_turns_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_turns_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],  # No grouping for accurate totals
                    filter_by=filter_by,
                ),
            )
        else:
            # If no grouping, only get totals (avoid duplicate query)
            turn_distribution_data = []
            turn_totals_data = analytics_repo.get_turns_summary(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )
        # Process Turn Distribution Data using generic architecture
        turn_distribution = process_analytics_data_generic(
            turn_distribution_data,
            ordered_group_by,
            AnalyticsReportType.MESSAGE_TURNS.metrics_config,
        )

        # Calculate turns totals from ungrouped data (accurate totals)
        turns_totals = process_analytics_data_generic(
            turn_totals_data,
            None,
            AnalyticsReportType.MESSAGE_TURNS.metrics_config,
            calculate_totals=True,
        )

        result = {
            "turn_distribution": turn_distribution,
            "totals": turns_totals,
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

        return result

    except Exception as e:
        logger.error(f"Error generating turns summary: {e}")
        raise


def get_calls_time_summary(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict:
    """
    Get call time metrics following the same pattern as get_turns_summary.

    Args:
        session: Database session
        start_date: Start date for analysis
        end_date: End date for analysis
        group_by: List of fields to group by ['date', 'account_id', 'project_id']
        filter_by: Dict of filters {'account_id': uuid|list[uuid], 'project_id': uuid|list[uuid]}

    Returns:
        dict: {
            'call_time_metrics': {...},
            'totals': {...},
            'metadata': {...}
        }
    """
    try:
        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Optimize database calls based on grouping requirements
        if ordered_group_by:
            # If grouping is requested, get both grouped and total data
            call_time_data, call_time_totals_data = (
                analytics_repo.get_calls_time_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_calls_time_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],  # No grouping for accurate totals
                    filter_by=filter_by,
                ),
            )
        else:
            # If no grouping, only get totals (avoid duplicate query)
            call_time_data = []
            call_time_totals_data = analytics_repo.get_calls_time_summary(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )
        # Process Call Time Data using generic architecture
        call_time_report = process_analytics_data_generic(
            call_time_data,
            ordered_group_by,
            AnalyticsReportType.CALL_METRICS.metrics_config,
        )

        # Calculate totals from ungrouped data (accurate totals)
        totals = process_analytics_data_generic(
            call_time_totals_data,
            None,
            AnalyticsReportType.CALL_METRICS.metrics_config,
            calculate_totals=True,
        )

        return {
            "call_time_metrics": call_time_report,
            "totals": totals,
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

    except Exception as e:
        logger.error(f"Error generating call time summary: {e}")
        raise


def get_calls_info_summary(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict:
    """Get call purpose and language distribution - simple like get_calls_time_summary."""
    try:
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order but exclude date
        filtered_group_by = [field for field in group_by if field != "date"]
        ordered_group_by = _enforce_hierarchy_order(filtered_group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Optimize database calls based on grouping requirements
        if ordered_group_by:
            # If grouping is requested, get both grouped and total data
            call_info_data, call_info_totals_data = (
                analytics_repo.get_calls_info_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_calls_info_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],  # No grouping for accurate totals
                    filter_by=filter_by,
                ),
            )
        else:
            # If no grouping, only get totals (avoid duplicate query)
            call_info_data = []
            call_info_totals_data = analytics_repo.get_calls_info_summary(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )
        # Process Call Purpose Distribution (purposes only)
        call_purpose_report = process_analytics_data_generic(
            call_info_data,
            ordered_group_by,
            AnalyticsReportType.CALL_PURPOSE_DISTRIBUTION.metrics_config,
        )

        # Process Call Language Distribution (languages only)
        call_language_report = process_analytics_data_generic(
            call_info_data,
            ordered_group_by,
            AnalyticsReportType.CALL_LANGUAGE_DISTRIBUTION.metrics_config,
        )

        # Calculate separate totals
        call_purpose_totals = process_analytics_data_generic(
            call_info_totals_data,
            None,
            AnalyticsReportType.CALL_PURPOSE_DISTRIBUTION.metrics_config,
            calculate_totals=True,
        )

        call_language_totals = process_analytics_data_generic(
            call_info_totals_data,
            None,
            AnalyticsReportType.CALL_LANGUAGE_DISTRIBUTION.metrics_config,
            calculate_totals=True,
        )

        return {
            "call_purpose_distribution": call_purpose_report,
            "call_language_distribution": call_language_report,
            "totals": {
                "purposes": call_purpose_totals,
                "languages": call_language_totals,
            },
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

    except Exception as e:
        logger.error(f"Error generating call info summary: {e}")
        raise


def get_conversion_summary(
    session: Session,
    start_date: datetime,
    end_date: datetime,
    group_by: list[str] | None = None,
    filter_by: dict[str, uuid.UUID | list[uuid.UUID]] | None = None,
) -> dict:
    """
    Get conversion metrics showing how many conversations lead to orders and paid orders.

    Args:
        session: Database session
        start_date: Start date for analysis
        end_date: End date for analysis
        group_by: List of fields to group by ['account_id', 'project_id'] (date is automatically prepended)
        filter_by: Dict of filters {'account_id': uuid|list[uuid], 'project_id': uuid|list[uuid]}

    Returns:
        dict: {
            'conversion_metrics': {...},
            'totals': {...},
            'metadata': {...}
        }
    """
    try:
        # group_by is required (can be empty list for totals only)
        if group_by is None:
            group_by = []

        # Enforce consistent hierarchy order: date -> account_id -> project_id
        ordered_group_by = _enforce_hierarchy_order(group_by)

        # Initialize repositories
        analytics_repo = db.AnalyticsRepository(session)

        # Optimize database calls based on grouping requirements
        if ordered_group_by:
            # If grouping is requested, get both grouped and total data
            conversion_data, conversion_totals_data = (
                analytics_repo.get_conversion_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=ordered_group_by,
                    filter_by=filter_by,
                ),
                analytics_repo.get_conversion_summary(
                    start_date=start_date,
                    end_date=end_date,
                    group_by=[],  # No grouping for accurate totals
                    filter_by=filter_by,
                ),
            )
        else:
            # If no grouping, only get totals (avoid duplicate query)
            conversion_data = []
            conversion_totals_data = analytics_repo.get_conversion_summary(
                start_date=start_date,
                end_date=end_date,
                group_by=[],
                filter_by=filter_by,
            )
        # Process Conversion Data using generic architecture
        conversion_report = process_analytics_data_generic(
            conversion_data,
            ordered_group_by,
            AnalyticsReportType.CONVERSION_METRICS.metrics_config,
        )

        # Calculate totals from ungrouped data (accurate totals)
        totals = process_analytics_data_generic(
            conversion_totals_data,
            None,
            AnalyticsReportType.CONVERSION_METRICS.metrics_config,
            calculate_totals=True,
        )

        return {
            "conversion_metrics": conversion_report,
            "totals": totals,
            "metadata": {
                "group_by": ordered_group_by,
                "filter_by": filter_by or {},
            },
        }

    except Exception as e:
        logger.error(f"Error generating conversion summary: {e}")
        raise
