"""Utility helpers for Slack report formatting."""

from collections.abc import Callable
from decimal import Decimal
from typing import TypedDict

TRANSFER_REASON_DISTRIBUTION_REPORT = "Transfer Reason Distribution"
CALL_QUALITY_DISTRIBUTION_REPORT = "Call Quality Distribution"


class ColumnConfig(TypedDict):
    """Column metadata used when rendering Slack report tables."""

    header: str
    data_key: str
    format_func: Callable[[object], str]


def safe_float_format(value: object, decimals: int = 1) -> str:
    """Safely format a value as float, handling strings and None."""
    if value is None:
        return "N/A"
    if not isinstance(value, (Decimal, float, int, str)):
        return str(value)
    try:
        return f"{float(value):.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


def format_percent_for_text(value: object, decimals: int = 1) -> str:
    """Format a percentage value for prose without appending '%' to N/A."""
    formatted = safe_float_format(value, decimals)
    if formatted == "N/A":
        return formatted
    return f"{formatted}%"


def format_rate_with_count(
    value: object,
    numerator: object,
    denominator: object,
    decimals: int = 1,
    include_percent: bool = True,
) -> str:
    """Format a rate alongside the raw count ratio that produced it."""
    formatted = safe_float_format(value, decimals)
    if include_percent and formatted != "N/A":
        formatted = f"{formatted}%"
    return f"{formatted} ({to_int(numerator)}/{to_int(denominator)})"


def to_int(value: object) -> int:
    """Convert numeric report values to int for derived metric aggregation."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (Decimal, float, int)):
        return int(value)
    if not isinstance(value, str):
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0


def calculate_rate(numerator: object, denominator: object) -> float | None:
    """Calculate a percentage rate, returning None when the denominator is zero."""
    denominator_int = to_int(denominator)
    if denominator_int <= 0:
        return None
    return round((to_int(numerator) / denominator_int) * 100, 1)


def get_distribution_group_name(row: dict[str, object]) -> str | None:
    """Return the group display name used by grouped distribution rows."""
    for group_name_key in ("account_name", "project_name"):
        group_name = row.get(group_name_key)
        if group_name is not None:
            return str(group_name)
    return None


def summarize_transfer_fault_by_group(
    rows: list[dict[str, object]],
) -> dict[str, dict[str, int]]:
    """Summarize transfer agent-fault counts by report group."""
    summary_by_group: dict[str, dict[str, int]] = {}

    for row in rows:
        group_name = get_distribution_group_name(row)
        if group_name is None:
            continue

        group_summary = summary_by_group.setdefault(
            group_name,
            {"transfer_agent_fault_calls": 0},
        )
        group_summary["transfer_agent_fault_calls"] += to_int(
            row.get("agent_fault_count")
        )

    return summary_by_group


def summarize_spam_by_group(
    rows: list[dict[str, object]],
) -> dict[str, dict[str, int]]:
    """Summarize non-legitimate call-quality counts by report group."""
    summary_by_group: dict[str, dict[str, int]] = {}

    for row in rows:
        group_name = get_distribution_group_name(row)
        is_legitimate = row.get("is_legitimate")
        if group_name is None or is_legitimate is not False:
            continue

        group_summary = summary_by_group.setdefault(group_name, {"spam_calls": 0})
        group_summary["spam_calls"] += to_int(row.get("count"))

    return summary_by_group


def apply_derived_engagement_rates(
    unified_accounts: dict[str, dict[str, object]],
) -> None:
    """Apply derived percentages that combine multiple analytics reports."""
    for account_data in unified_accounts.values():
        total_calls = account_data.get("total_calls", 0)
        transfer_calls = account_data.get("transfer_calls", 0)

        account_data["negative_sentiment_rate"] = calculate_rate(
            account_data.get("negative_calls", 0),
            total_calls,
        )
        account_data["transfer_agent_fault_rate"] = calculate_rate(
            account_data.get("transfer_agent_fault_calls", 0),
            transfer_calls,
        )
        account_data["spam_rate"] = calculate_rate(
            account_data.get("spam_calls", 0),
            total_calls,
        )


def apply_derived_totals(totals_summary: dict[str, dict[str, object]]) -> None:
    """Apply derived engagement totals used by Slack summary formatting."""
    call_totals = totals_summary.get("Call Time Metrics")
    if not call_totals:
        return

    total_calls = call_totals.get("total_calls", 0)
    total_transfers = call_totals.get("total_transfer_calls", 0)

    transfer_reason_totals = totals_summary.get(TRANSFER_REASON_DISTRIBUTION_REPORT, {})
    call_quality_totals = totals_summary.get(CALL_QUALITY_DISTRIBUTION_REPORT, {})

    call_totals["negative_sentiment_rate"] = calculate_rate(
        call_totals.get("total_negative_calls", 0),
        total_calls,
    )
    call_totals["transfer_agent_fault_calls"] = to_int(
        transfer_reason_totals.get("agent_fault_calls")
    )
    call_totals["transfer_agent_fault_rate"] = calculate_rate(
        call_totals["transfer_agent_fault_calls"],
        total_transfers,
    )
    call_totals["spam_calls"] = to_int(
        call_quality_totals.get("total_non_legitimate_calls")
    )
    call_totals["spam_rate"] = calculate_rate(
        call_totals["spam_calls"],
        total_calls,
    )


def create_column_config(
    key: str, header: str, format_type: str = "int"
) -> ColumnConfig:
    """Create a standardized column configuration."""
    format_funcs: dict[str, Callable[[object], str]] = {
        "int": lambda x: str(x) if x is not None else "N/A",
        "float": lambda x: safe_float_format(x, 1),
        "percent": lambda x: f"{safe_float_format(x, 1)}%" if x is not None else "N/A",
        "currency": lambda x: f"${safe_float_format(x, 2)}" if x is not None else "N/A",
        "duration": lambda x: f"{safe_float_format(x, 1)}s" if x is not None else "N/A",
    }

    return {
        "header": header,
        "data_key": key,
        "format_func": format_funcs.get(format_type, format_funcs["int"]),
    }
