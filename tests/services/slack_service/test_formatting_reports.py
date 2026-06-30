import re

from api.schemas.admin.analytics import PerformanceReport
from services.slack_service._formatting import (
    _create_engagement_table_generic,
    format_unified_report_for_slack,
    merge_report_data,
)


def _engagement_metric_reports() -> list[PerformanceReport]:
    return [
        PerformanceReport(
            name="Call Time Metrics",
            data={
                "call_time_metrics": {
                    "Acme": {
                        "total_calls": 10,
                        "avg_duration": 42.25,
                        "transfer_calls": 4,
                        "transfer_rate": 40.0,
                        "positive_calls": 6,
                        "neutral_calls": 2,
                        "negative_calls": 2,
                    },
                    "No Transfers": {
                        "total_calls": 5,
                        "avg_duration": 13.0,
                        "transfer_calls": 0,
                        "transfer_rate": 0.0,
                        "positive_calls": 5,
                        "neutral_calls": 0,
                        "negative_calls": 0,
                    },
                },
                "totals": {
                    "total_calls": 15,
                    "avg_duration": 32.5,
                    "total_transfer_calls": 4,
                    "overall_transfer_rate": 26.7,
                    "total_positive_calls": 11,
                    "total_neutral_calls": 2,
                    "total_negative_calls": 2,
                },
            },
        ),
        PerformanceReport(
            name="Transfer Reason Distribution",
            data={
                "transfer_reason_distribution": [
                    {
                        "account_name": "Acme",
                        "reason": "tool_failure_order",
                        "count": 3,
                        "agent_fault_count": 1,
                    },
                    {
                        "account_name": "Acme",
                        "reason": "cold_opt_out",
                        "count": 1,
                        "agent_fault_count": 0,
                    },
                ],
                "totals": {
                    "total_transfer_reason_calls": 4,
                    "agent_fault_calls": 1,
                    "agent_fault_rate": 25.0,
                    "transfer_reason_distribution": [],
                },
            },
        ),
        PerformanceReport(
            name="Call Quality Distribution",
            data={
                "call_quality_distribution": [
                    {
                        "account_name": "Acme",
                        "call_quality_label": "legitimate_restaurant_call",
                        "count": 8,
                        "is_legitimate": True,
                    },
                    {
                        "account_name": "Acme",
                        "call_quality_label": "spam_scam",
                        "count": 2,
                        "is_legitimate": False,
                    },
                    {
                        "account_name": "No Transfers",
                        "call_quality_label": "legitimate_restaurant_call",
                        "count": 5,
                        "is_legitimate": True,
                    },
                ],
                "totals": {
                    "total_call_quality_calls": 15,
                    "total_legitimate_calls": 13,
                    "total_non_legitimate_calls": 2,
                    "legitimate_rate": 86.7,
                    "non_legitimate_rate": 13.3,
                    "call_quality_distribution": [],
                },
            },
        ),
    ]


def test_merge_report_data_adds_requested_engagement_metric_rates() -> None:
    merged_data = merge_report_data(_engagement_metric_reports())

    acme_metrics = merged_data["unified_accounts"]["Acme"]
    assert acme_metrics["negative_sentiment_rate"] == 20.0
    assert acme_metrics["transfer_agent_fault_calls"] == 1
    assert acme_metrics["transfer_agent_fault_rate"] == 25.0
    assert acme_metrics["spam_calls"] == 2
    assert acme_metrics["spam_rate"] == 20.0

    no_transfer_metrics = merged_data["unified_accounts"]["No Transfers"]
    assert no_transfer_metrics["negative_sentiment_rate"] == 0.0
    assert no_transfer_metrics["transfer_agent_fault_rate"] is None
    assert no_transfer_metrics["spam_rate"] == 0.0

    call_totals = merged_data["totals_summary"]["Call Time Metrics"]
    assert call_totals["negative_sentiment_rate"] == 13.3
    assert call_totals["transfer_agent_fault_calls"] == 1
    assert call_totals["transfer_agent_fault_rate"] == 25.0
    assert call_totals["spam_calls"] == 2
    assert call_totals["spam_rate"] == 13.3


def test_format_unified_report_replaces_resolution_with_requested_columns() -> None:
    blocks = format_unified_report_for_slack(_engagement_metric_reports())["blocks"]
    report_text = "\n".join(block["text"]["text"] for block in blocks)

    assert "Res w/o Xfer" not in report_text
    assert "Resolution without Transfer Rate" not in report_text
    assert "Negative Sentiment" in report_text
    assert "Transfer w Agent Fault" in report_text
    assert "Spam %" in report_text
    assert (
        "Transfer Rate 26.7%, Negative Sentiment 13.3% (2/15), "
        "Transfer w Agent Fault 25.0% (1/4), Spam 13.3% (2/15)"
    ) in report_text
    assert re.search(
        r"^Acme\s+0\s+0\s+10\s+42\.2\s+40\.0\s+"
        r"20\.0% \(2/10\)\s+25\.0% \(1/4\)\s+20\.0% \(2/10\)$",
        report_text,
        re.MULTILINE,
    )


def test_merge_report_data_keeps_missing_analysis_in_denominator_only() -> None:
    reports = [
        PerformanceReport(
            name="Call Time Metrics",
            data={
                "call_time_metrics": {
                    "Missing Analysis": {
                        "total_calls": 4,
                        "avg_duration": 10.0,
                        "transfer_calls": 1,
                        "transfer_rate": 25.0,
                        "positive_calls": 0,
                        "neutral_calls": 0,
                        "negative_calls": 1,
                    }
                },
                "totals": {
                    "total_calls": 4,
                    "avg_duration": 10.0,
                    "total_transfer_calls": 1,
                    "overall_transfer_rate": 25.0,
                    "total_positive_calls": 0,
                    "total_neutral_calls": 0,
                    "total_negative_calls": 1,
                },
            },
        ),
        PerformanceReport(
            name="Transfer Reason Distribution",
            data={
                "transfer_reason_distribution": [
                    {
                        "account_name": "Missing Analysis",
                        "reason": "Missing Analysis",
                        "count": 1,
                        "agent_fault_count": 0,
                    }
                ],
                "totals": {
                    "total_transfer_reason_calls": 1,
                    "agent_fault_calls": 0,
                    "agent_fault_rate": 0.0,
                    "transfer_reason_distribution": [],
                },
            },
        ),
        PerformanceReport(
            name="Call Quality Distribution",
            data={
                "call_quality_distribution": [
                    {
                        "account_name": "Missing Analysis",
                        "call_quality_label": "unknown_unclear",
                        "count": 3,
                        "is_legitimate": None,
                    },
                    {
                        "account_name": "Missing Analysis",
                        "call_quality_label": "spam_scam",
                        "count": 1,
                        "is_legitimate": False,
                    },
                ],
                "totals": {
                    "total_call_quality_calls": 4,
                    "total_legitimate_calls": 0,
                    "total_non_legitimate_calls": 1,
                    "legitimate_rate": 0.0,
                    "non_legitimate_rate": 25.0,
                    "call_quality_distribution": [],
                },
            },
        ),
    ]

    merged_data = merge_report_data(reports)

    account_metrics = merged_data["unified_accounts"]["Missing Analysis"]
    assert account_metrics["negative_sentiment_rate"] == 25.0
    assert account_metrics["transfer_agent_fault_rate"] == 0.0
    assert account_metrics["spam_calls"] == 1
    assert account_metrics["spam_rate"] == 25.0

    call_totals = merged_data["totals_summary"]["Call Time Metrics"]
    assert call_totals["negative_sentiment_rate"] == 25.0
    assert call_totals["transfer_agent_fault_rate"] == 0.0
    assert call_totals["spam_calls"] == 1
    assert call_totals["spam_rate"] == 25.0


def test_engagement_table_shows_na_for_zero_rate_denominators() -> None:
    table = _create_engagement_table_generic(
        {
            "No Calls": {
                "active_users": 0,
                "total_conversations": 0,
                "total_calls": 0,
                "avg_duration": 0,
                "transfer_rate": 0,
                "negative_sentiment_rate": None,
                "transfer_agent_fault_rate": None,
                "spam_rate": None,
            }
        }
    )

    no_calls_row = next(line for line in table.splitlines() if "No Calls" in line)
    assert no_calls_row.count("N/A") == 3
