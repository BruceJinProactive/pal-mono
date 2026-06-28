from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from db.tables.types import CallQualityLabel
from utils.log import logger


@dataclass(frozen=True)
class TransferReasonMetadata:
    key: str
    label: str
    description: str
    prompt_description: str
    agent_fault_default: bool | None


@dataclass(frozen=True)
class CallQualityMetadata:
    key: str
    label: str
    description: str
    prompt_description: str
    is_legitimate: bool

    @property
    def value(self) -> str:
        return self.key


TRANSFER_REASON_METADATA: tuple[TransferReasonMetadata, ...] = (
    TransferReasonMetadata(
        key="cold_opt_out",
        label="Cold opt-out",
        description="Generic request to speak with a human",
        prompt_description=(
            "The caller's first substantive utterance is a generic human "
            'request, such as "representative" or "speak to a person." Do not '
            "use this if the caller first stated another intent, or if the "
            "caller asked for a named/specific person or department."
        ),
        agent_fault_default=False,
    ),
    TransferReasonMetadata(
        key="capability_specific_person",
        label="Specific person",
        description="Asked for a named employee or manager",
        prompt_description=(
            "Caller asks for a named employee, manager, front desk, or specific "
            "person."
        ),
        agent_fault_default=False,
    ),
    TransferReasonMetadata(
        key="user_frustration_in_flow",
        label="Flow frustration",
        description="Repetition or missed details led to transfer",
        prompt_description=(
            "No explicit tool error, but repetition, missed details, or flow "
            "breakdown made the caller ask for a human."
        ),
        agent_fault_default=True,
    ),
    TransferReasonMetadata(
        key="capability_reservation",
        label="Reservation support",
        description="Reservation request needed human help",
        prompt_description=(
            "Agent says it cannot book or fully handle reservations and offers "
            "transfer."
        ),
        agent_fault_default=False,
    ),
    TransferReasonMetadata(
        key="tool_failure_order",
        label="Order tool failure",
        description="Ordering, checkout, or payment tool failed",
        prompt_description=(
            "Agent was placing/finalizing an order or checkout and a "
            "tool/order/payment/link-delivery error caused transfer. This "
            "includes cases where the caller did not receive an ordering or "
            "payment link."
        ),
        agent_fault_default=True,
    ),
    TransferReasonMetadata(
        key="capability_catering",
        label="Catering",
        description="Large-party or event order needed staff",
        prompt_description=(
            "Catering, large party, or event order the agent cannot fully handle."
        ),
        agent_fault_default=False,
    ),
    TransferReasonMetadata(
        key="other",
        label="Other",
        description="Transfer reason outside the main categories",
        prompt_description="Use only when the transfer happened but none of the above fit.",
        agent_fault_default=False,
    ),
    TransferReasonMetadata(
        key="post_order_followup",
        label="Post-order follow-up",
        description="Follow-up after order or payment link",
        prompt_description=(
            "Order/payment link was already created, then caller asked for a "
            "human to confirm, modify, complain, or follow up."
        ),
        agent_fault_default=False,
    ),
    TransferReasonMetadata(
        key="capability_other_department",
        label="Other department",
        description="Billing, corporate, supplier, or similar",
        prompt_description=(
            "Billing, corporate, supplier, accounts payable, or another "
            "non-restaurant department."
        ),
        agent_fault_default=False,
    ),
    TransferReasonMetadata(
        key="checkout_handoff_not_human",
        label="Checkout handoff",
        description="Self-service handoff rather than staff transfer",
        prompt_description=(
            "Transcript says the order/reservation was handed off for checkout, "
            "final processing, payment link, or self-service booking, but no "
            "human transfer actually occurred. Use this category instead of "
            "null when a transfer signal exists but the handoff was not to a "
            "human."
        ),
        agent_fault_default=False,
    ),
    TransferReasonMetadata(
        key="ambiguous_intent_user_gave_up",
        label="Ambiguous intent",
        description="Caller did not provide a usable request",
        prompt_description=(
            "Caller request was unclear, caller only greeted / checked "
            "connection, or agent asked for clarification and the call "
            "transferred before the caller gave a usable intent."
        ),
        agent_fault_default=False,
    ),
    TransferReasonMetadata(
        key="capability_hiring",
        label="Hiring",
        description="Job or employment inquiry",
        prompt_description="Job, hiring, or employment inquiry.",
        agent_fault_default=False,
    ),
    TransferReasonMetadata(
        key="failed_transfer_attempt",
        label="Failed transfer",
        description="Agent could not complete the transfer",
        prompt_description=(
            "Agent failed to connect, reported transfer could not happen, or "
            "initially refused to transfer before complying."
        ),
        agent_fault_default=True,
    ),
    TransferReasonMetadata(
        key="capability_off_topic",
        label="Off topic",
        description="Wrong business or unrelated request",
        prompt_description="Wrong business or unrelated to restaurant operations.",
        agent_fault_default=False,
    ),
)
TRANSFER_REASON_CATEGORIES: tuple[str, ...] = tuple(
    metadata.key for metadata in TRANSFER_REASON_METADATA
)
TRANSFER_REASON_METADATA_BY_KEY: dict[str, TransferReasonMetadata] = {
    metadata.key: metadata for metadata in TRANSFER_REASON_METADATA
}


CALL_QUALITY_LABEL_METADATA: tuple[CallQualityMetadata, ...] = (
    CallQualityMetadata(
        key=CallQualityLabel.legitimate_restaurant_call.value,
        label="Legit calls",
        description="Real restaurant or customer-service intent",
        prompt_description=(
            "A real caller asking about the restaurant, menu, ordering, "
            "reservations, hours, delivery, complaints, or another legitimate "
            "restaurant/customer-service matter."
        ),
        is_legitimate=True,
    ),
    CallQualityMetadata(
        key=CallQualityLabel.robot_prerecorded.value,
        label="Robot / prerecorded",
        description="Automated, synthetic, IVR, or prerecorded caller",
        prompt_description=(
            "Prerecorded, synthetic, IVR, auto-dialer, or bot-like speech that "
            "is not trying to have a normal restaurant conversation."
        ),
        is_legitimate=False,
    ),
    CallQualityMetadata(
        key=CallQualityLabel.promotional_sales.value,
        label="Promotional sales",
        description="Vendor, marketing, supplier, recruiting, or sales outreach",
        prompt_description=(
            "Sales, marketing, vendor, recruiting, supplier, SEO, financing, "
            "or other promotional outreach to the restaurant rather than a "
            "customer checking on restaurant services."
        ),
        is_legitimate=False,
    ),
    CallQualityMetadata(
        key=CallQualityLabel.spam_scam.value,
        label="Spam / scam",
        description="Suspicious, fraudulent, phishing, or spam-like caller",
        prompt_description=(
            "Likely scam, phishing, fraud, spoofing, suspicious lead-gen, or "
            "other spam unrelated to legitimate restaurant operations."
        ),
        is_legitimate=False,
    ),
    CallQualityMetadata(
        key=CallQualityLabel.prank_or_abusive.value,
        label="Prank or abusive",
        description="Prank, harassment, abusive, or intentionally disruptive call",
        prompt_description=(
            "Prank, harassment, abusive language, or intentionally disruptive "
            "call with no legitimate restaurant purpose."
        ),
        is_legitimate=False,
    ),
    CallQualityMetadata(
        key=CallQualityLabel.unknown_unclear.value,
        label="Unknown / unclear",
        description="Silence, no usable caller speech, or insufficient evidence",
        prompt_description=(
            "Insufficient evidence to classify the call quality with confidence."
        ),
        is_legitimate=False,
    ),
)
CALL_QUALITY_METADATA: tuple[CallQualityMetadata, ...] = CALL_QUALITY_LABEL_METADATA
CALL_QUALITY_METADATA_BY_VALUE: dict[str, CallQualityMetadata] = {
    metadata.value: metadata for metadata in CALL_QUALITY_METADATA
}
CALL_QUALITY_REASON_CODES: tuple[str, ...] = (
    "restaurant_intent_present",
    "caller_asked_restaurant_question",
    "order_or_reservation_intent",
    "no_user_audio",
    "assistant_only_transcript",
    "only_background_noise_or_dead_air",
    "empty_or_near_empty_transcript",
    "prerecorded_or_synthetic_voice",
    "repeated_script_or_bot_behavior",
    "sales_or_vendor_outreach",
    "generic_marketing_pitch",
    "scam_or_phishing_attempt",
    "wrong_number_or_misdial",
    "off_topic_non_restaurant",
    "abusive_or_prank_language",
    "insufficient_evidence",
    "live_close_reason_silence_timeout",
)


def format_transfer_reason_taxonomy_for_prompt() -> str:
    """Return transfer reason taxonomy lines for the post-call analytics prompt."""
    return "\n".join(
        f"   - {metadata.key}: {metadata.prompt_description}"
        for metadata in TRANSFER_REASON_METADATA
    )


def format_transfer_agent_fault_defaults_for_prompt() -> str:
    """Return transfer-agent fault defaults for the post-call analytics prompt."""
    true_categories = [
        metadata.key
        for metadata in TRANSFER_REASON_METADATA
        if metadata.agent_fault_default is True
    ]
    false_categories = [
        metadata.key
        for metadata in TRANSFER_REASON_METADATA
        if metadata.agent_fault_default is False
    ]

    return "\n".join(
        [
            f"   - true for: {', '.join(true_categories)}.",
            f"   - false for: {', '.join(false_categories)}.",
            "   - null when transfer_reason_category is null.",
        ]
    )


def format_call_quality_taxonomy_for_prompt() -> str:
    """Return call-quality taxonomy lines for the post-call analytics prompt."""
    return "\n".join(
        f"   - {metadata.key}: {metadata.prompt_description}"
        for metadata in CALL_QUALITY_LABEL_METADATA
    )


# =============================================================================
# TIME RELATED FUNCTIONS
# =============================================================================
def validate_date_range(
    start_date: datetime | None, end_date: datetime | None
) -> tuple[datetime, datetime]:
    "Validate that start_date is before end_date if both are provided."
    "If either is None, set defaults to today."
    start_today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end_today = datetime.utcnow().replace(
        hour=23, minute=59, second=59, microsecond=999999
    )
    if start_date is None and end_date is None:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
    if start_date is None:
        start_date = start_today
    if end_date is None:
        end_date = end_today
    if start_date > end_date:
        start_date, end_date = datetime.utcnow(), datetime.utcnow()

    # convert time to UTC to avoid DST issues
    start_date, end_date = (
        normalize_datetime_to_utc(start_date),
        normalize_datetime_to_utc(end_date),
    )
    return start_date, end_date


def normalize_datetime_to_utc(dt: datetime) -> datetime:
    """
    Convert datetime to UTC timezone.

    Args:
        dt: Datetime to convert. Can be naive (no timezone) or timezone-aware.

    Returns:
        datetime | None: UTC datetime or None if input was None

    Behavior:
        - If dt is None: returns None
        - If dt is naive (no timezone): assumes UTC and adds UTC timezone
        - If dt has timezone: converts to UTC
    """
    if dt.tzinfo is None:
        # Naive datetime - assume UTC
        return dt.replace(tzinfo=UTC)
    else:
        # Has timezone - convert to UTC
        return dt.astimezone(UTC)


# =============================================================================
# SLACK REPORTING FUNCTIONS
# =============================================================================
def build_slack_report_blocks(report: list[dict]) -> list[dict]:
    """Convert report JSON into Slack Block Kit blocks."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Split out TOTAL row
    total = next((r for r in report if r["account_name"].upper() == "TOTAL"), None)
    accounts = [r for r in report if r["account_name"].upper() != "TOTAL"]

    # Header + context
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📊 Palona • Daily Commerce Report"},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Generated on: {now}"}],
        },
        {"type": "divider"},
    ]

    # TOTAL summary
    if total:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*🚀 Summary (TOTAL)*\n"
                        f"• Conversations: *{total['total_conversations']}*\n"
                        f"• Orders: *{total['conversations_with_orders']}*\n"
                        f"• Paid Orders: *{total['conversations_with_paid_orders']}*\n"
                        f"• Checkout Link Conversion Rate: *{total['checkout_conversion_rate']:.2f}%*\n"
                        f"• Payment From Link Rate: *{total['paid_rate']:.2f}%*"
                    ),
                },
            }
        )
        blocks.append({"type": "divider"})

        # Build the table with consistent column spacing
    if accounts:
        # Compute dynamic column widths from values and headers
        name_width = max(
            max(len(r["account_name"]) for r in accounts) + 2, len("Account"), 20
        )

        conv_width = max(
            len("Conv"),
            max(len(str(r["total_conversations"])) for r in accounts),
        )
        orders_width = max(
            len("Orders"),
            max(len(str(r["conversations_with_orders"])) for r in accounts),
        )
        paid_width = max(
            len("Paid"),
            max(len(str(r["conversations_with_paid_orders"])) for r in accounts),
        )

        cvr_values = [f"{r['checkout_conversion_rate']:.1f}" for r in accounts]
        rate_values = [f"{r['paid_rate']:.1f}" for r in accounts]
        cvr_width = max(len("Link CVR%"), max(len(v) for v in cvr_values))
        rate_width = max(len("Link Paid%"), max(len(v) for v in rate_values))

        # Define consistent spacing between columns
        col_spacing = "  "  # 2 spaces between columns

        # Build header with dynamic widths and consistent spacing
        header = (
            f"{'Account':<{name_width}}{col_spacing}"
            f"{'Conv':>{conv_width}}{col_spacing}"
            f"{'Orders':>{orders_width}}{col_spacing}"
            f"{'Paid':>{paid_width}}{col_spacing}"
            f"{'Link CVR%':>{cvr_width}}{col_spacing}"
            f"{'Link Paid%':>{rate_width}}\n"
        )

        # Calculate total width for separator
        total_width = (
            name_width
            + conv_width
            + orders_width
            + paid_width
            + cvr_width
            + rate_width
            + (len(col_spacing) * 5)
        )
        separator = "-" * total_width + "\n"

        rows = []
        for r in accounts:
            rows.append(
                f"{r['account_name']:<{name_width}}{col_spacing}"
                f"{r['total_conversations']:>{conv_width}}{col_spacing}"
                f"{r['conversations_with_orders']:>{orders_width}}{col_spacing}"
                f"{r['conversations_with_paid_orders']:>{paid_width}}{col_spacing}"
                f"{r['checkout_conversion_rate']:>{cvr_width}.1f}{col_spacing}"
                f"{r['paid_rate']:>{rate_width}.1f}"
            )

        table_text = "```" + header + separator + "\n".join(rows) + "```"

        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Per Account Breakdown*\n" + table_text,
                },
            }
        )

    # Footer context
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Link CVR% = orders / conversations · Link Paid% = paid orders / orders",
                }
            ],
        }
    )

    return blocks


# =============================================================================
# GENERIC ANALYTICS DATA PROCESSING ARCHITECTURE
# =============================================================================

# Field mapping configuration for complex field handling
FIELD_MAPPING_CONFIG = {
    "account_id": {
        "skip_fields": 2,  # Skip account_id, use account_name
        "value_index": 1,  # Use the second field (account_name)
    },
    "project_id": {
        "skip_fields": 2,  # Skip project_id, use project_name
        "value_index": 1,  # Use the second field (project_name)
    },
    "date": {
        "skip_fields": 1,
        "value_index": 0,
        "formatter": lambda value: (
            value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)
        ),
    },
}


def _enforce_hierarchy_order(group_by: list[str] | None) -> list[str]:
    """
    Enforce consistent hierarchy order: date -> account_id -> project_id.

    Args:
        group_by: List of grouping fields in any order

    Returns:
        List of grouping fields in enforced hierarchy order
    """
    if not group_by:
        return []

    # Define the consistent hierarchy order
    hierarchy_order = ["date", "account_id", "project_id"]

    # Filter and reorder group_by to match hierarchy
    return [field for field in hierarchy_order if field in group_by]


def create_metrics_processor(metrics_config: dict):
    """
    Factory function to create metrics processors for different report types.

    Args:
        metrics_config: Configuration dict defining how to extract metrics from row

    Returns:
        callable: Function that processes a row and returns metrics dict

    Example metrics_config:
        {
            "active_users": {"source": "row_index", "index": -2},
            "total_conversations": {"source": "row_index", "index": -1},
            "conversion_rate": {
                "source": "calculated",
                "formula": lambda row: row[-2] / row[-1] if row[-1] > 0 else 0
            }
        }
    """

    def metrics_processor(row: tuple) -> dict:
        result = {}

        for metric_name, config in metrics_config.items():
            if config["source"] == "row_index":
                value = row[config["index"]]
                # Preserve original numeric type (int, float, Decimal, etc.)
                result[metric_name] = value if value is not None else 0
            elif config["source"] == "calculated":
                try:
                    result[metric_name] = config["formula"](row)
                except (ValueError, TypeError, ZeroDivisionError) as e:
                    logger.warning(
                        f"Error calculating metric {metric_name}: {e}, using 0"
                    )
                    result[metric_name] = 0
            elif config["source"] == "raw":
                result[metric_name] = row[config["index"]]

        return result

    return metrics_processor


def process_analytics_data_generic(
    data: list[tuple],
    group_by: list[str] | None,
    metrics_config: dict,
    calculate_totals: bool = False,
) -> dict:
    """
    Generic function to process analytics data into nested hierarchical structure OR flat totals.

    Args:
        data: List of tuples from database query
        group_by: List of grouping field names (ignored if calculate_totals=True)
        metrics_config: Configuration dict for extracting metrics from each row
        calculate_totals: If True, returns flat totals; if False, returns grouped data

    Returns:
        dict: Either nested dictionary structure or flat totals based on calculate_totals parameter

    Example usage:
        # For grouped data
        result = process_analytics_data_generic(data, group_by, metrics_config)

        # For totals
        totals = process_analytics_data_generic(data, None, metrics_config, calculate_totals=True)
    """
    if not data:
        return {}

    if calculate_totals:
        # Totals mode - flat aggregation
        totals = {}

        for metric_name, config in metrics_config.items():
            if config["source"] == "row_index":
                # Simple sum aggregation for row_index metrics
                index = config["index"]
                total_value = sum(
                    (row[index] if row[index] is not None else 0) for row in data
                )

                # Auto-generate total name
                total_name = (
                    f"total_{metric_name}"
                    if not metric_name.startswith("total_")
                    else metric_name
                )
                totals[total_name] = int(total_value)

            elif config["source"] == "calculated":
                # Smart aggregation for calculated metrics
                totals.update(_calculate_aggregated_metric(metric_name, data))

        return totals

    else:
        # Grouped mode - hierarchical structure
        if not group_by:
            return {}

        # Create metrics processor from config
        metrics_processor = create_metrics_processor(metrics_config)
        result = {}

        for row in data:
            current_level = result
            actual_field_index = 0

            # Navigate through each grouping level
            for field_index, field_name in enumerate(group_by):
                # Get field configuration
                field_config = FIELD_MAPPING_CONFIG.get(
                    field_name,
                    {"skip_fields": 1, "value_index": 0},
                )

                # Extract and format the value
                raw_value = row[actual_field_index + field_config["value_index"]]

                # Apply custom formatter if available
                if "formatter" in field_config:
                    formatted_value = field_config["formatter"](raw_value)
                else:
                    formatted_value = str(raw_value)

                # Move to next field position
                actual_field_index += field_config["skip_fields"]

                is_leaf_node = field_index == len(group_by) - 1

                if is_leaf_node:
                    # Leaf node - store processed metrics
                    current_level[formatted_value] = metrics_processor(row)
                else:
                    # Intermediate node - create nested dict and navigate deeper
                    current_level = current_level.setdefault(formatted_value, {})

        return result


def _calculate_aggregated_metric(metric_name: str, data: list) -> dict:
    """
    Calculate aggregated values for calculated metrics.
    Uses metric name patterns to determine aggregation logic.
    """
    if not data:
        logger.warning(f"No data provided for {metric_name} calculation")
        return {}

    result = {}
    is_grouped = data and len(data[0]) > 6

    # === AVERAGE METRICS ===
    if "avg_turns" in metric_name:
        total_turns = sum((row[-1] if row[-1] is not None else 0) for row in data)
        total_conversations = sum(
            (row[-2] if row[-2] is not None else 0) for row in data
        )
        result["avg_turns_per_conversation"] = (
            round(total_turns / total_conversations, 2)
            if total_conversations > 0
            else 0.0
        )

    elif "avg_duration" in metric_name:
        total_duration_sum = sum(
            (row[-9] if row[-9] is not None else 0)
            * (row[-10] if row[-10] is not None else 0)
            for row in data
        )
        total_calls = sum((row[-10] if row[-10] is not None else 0) for row in data)
        result["avg_duration"] = (
            round(total_duration_sum / total_calls, 2) if total_calls > 0 else 0.0
        )

    elif "avg_turn_latency" in metric_name:
        total_turn_latency_sum = sum(
            (row[-8] if row[-8] is not None else 0)
            * (row[-10] if row[-10] is not None else 0)
            for row in data
        )
        total_calls = sum((row[-10] if row[-10] is not None else 0) for row in data)
        result["avg_turn_latency"] = (
            round(total_turn_latency_sum / total_calls, 2) if total_calls > 0 else 0.0
        )

    # === RATE METRICS ===
    elif "transfer_rate" in metric_name:
        total_transfers = sum((row[-5] if row[-5] is not None else 0) for row in data)
        total_calls = sum((row[-10] if row[-10] is not None else 0) for row in data)
        result["overall_transfer_rate"] = (
            round(total_transfers / total_calls * 100, 1) if total_calls > 0 else 0.0
        )

    elif "conversion_rate" in metric_name:
        # Conversion rate: conversations_with_orders / total_conversations * 100
        # Indices for 7-field conversion query: -7=total_conversations, -6=conversations_with_orders
        total_orders = sum((row[-6] if row[-6] is not None else 0) for row in data)
        total_conversations = sum(
            (row[-7] if row[-7] is not None else 0) for row in data
        )

        result["overall_conversion_rate"] = (
            round(total_orders / total_conversations * 100, 2)
            if total_conversations > 0
            else 0.0
        )

        logger.debug(
            f"Conversion rate calculation: orders={total_orders}, conversations={total_conversations}, "
            f"rate={result['overall_conversion_rate']}% (grouped={is_grouped})"
        )

    elif "paid_rate" in metric_name:
        # Paid rate: paid_orders / conversations_with_orders * 100
        # Indices for 7-field conversion query: -5=paid_orders, -6=conversations_with_orders
        total_paid = sum((row[-5] if row[-5] is not None else 0) for row in data)
        total_orders = sum(
            (row[-6] if row[-6] is not None else 0) for row in data
        )  # conversations_with_orders

        result["overall_paid_rate"] = (
            round(total_paid / total_orders * 100, 2) if total_orders > 0 else 0.0
        )

        logger.debug(
            f"Paid rate calculation: paid={total_paid}, orders={total_orders}, "
            f"rate={result['overall_paid_rate']}% (grouped={is_grouped})"
        )

    elif "reservation_rate" in metric_name:
        # Reservation rate: total_reservations / total_conversations * 100
        total_reservations = sum(
            (row[-2] if row[-2] is not None else 0) for row in data
        )
        total_conversations = sum(
            (row[-7] if row[-7] is not None else 0) for row in data
        )
        result["overall_reservation_rate"] = (
            round(total_reservations / total_conversations * 100, 2)
            if total_conversations > 0
            else 0.0
        )

        logger.debug(
            f"Reservation rate calculation: reservations={total_reservations}, "
            f"conversations={total_conversations}, "
            f"rate={result['overall_reservation_rate']}% (grouped={is_grouped})"
        )

    elif "waitlist_rate" in metric_name:
        # Waitlist rate: total_waitlists / total_conversations * 100
        total_waitlists = sum((row[-1] if row[-1] is not None else 0) for row in data)
        total_conversations = sum(
            (row[-7] if row[-7] is not None else 0) for row in data
        )
        result["overall_waitlist_rate"] = (
            round(total_waitlists / total_conversations * 100, 2)
            if total_conversations > 0
            else 0.0
        )

        logger.debug(
            f"Waitlist rate calculation: waitlists={total_waitlists}, "
            f"conversations={total_conversations}, "
            f"rate={result['overall_waitlist_rate']}% (grouped={is_grouped})"
        )

    # === MONETARY TOTALS ===
    elif "total_subtotal" in metric_name:
        # Sum of all order subtotals (regardless of status)
        # Index for 7-field conversion query: -4=total_subtotal
        total_subtotal = sum(
            (float(row[-4]) if row[-4] is not None else 0.0) for row in data
        )
        result["total_subtotal"] = round(total_subtotal, 2)

    elif "paid_total" in metric_name:
        # Sum of subtotals from paid orders only
        # Index for 7-field conversion query: -3=paid_total
        paid_total = sum(
            (float(row[-3]) if row[-3] is not None else 0.0) for row in data
        )
        result["total_paid_total"] = round(paid_total, 2)

    return result


# =============================================================================
# LLM CALL ANALYTICS EXTRACTION
# =============================================================================


def _format_message_content(content: object) -> str:
    """Extract readable text from the message content shapes used by LiveKit."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [_format_message_content(part) for part in content]
        return " ".join(part for part in parts if part).strip()
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, dict):
            return _format_message_content(text.get("body"))
        if text is not None:
            return _format_message_content(text)
        for key in ("body", "content"):
            value = content.get(key)
            if value is not None:
                return _format_message_content(value)
        return ""
    return str(content)


def _format_conversation(conversation_history: list[dict]) -> str:
    """
    Format conversation history into a readable text format for LLM analysis.

    Args:
        conversation_history: List of message dicts with 'role' and 'content'

    Returns:
        Formatted conversation string
    """
    formatted_lines = []
    for msg in conversation_history:
        role = msg.get("role", "unknown")
        content = _format_message_content(msg.get("content", ""))
        formatted_lines.append(f"{role.upper()}: {content}")

    return "\n".join(formatted_lines)


def _normalize_transfer_reason_category(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("transfer_reason_category must be a string or null")

    normalized = value.strip()
    if normalized.lower() in {"", "none", "null", "not_applicable"}:
        return None
    if normalized not in TRANSFER_REASON_CATEGORIES:
        raise ValueError(f"Invalid transfer_reason_category: {normalized}")
    return normalized


def _normalize_transfer_agent_was_at_fault(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "none", "null", "not_applicable"}:
            return None
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ValueError("transfer_agent_was_at_fault must be a boolean or null")


def _normalize_call_quality_reason_codes(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("call_quality_reason_codes must be a list of strings")

    normalized_codes: list[str] = []
    for code in value:
        if not isinstance(code, str):
            raise ValueError("call_quality_reason_codes must be a list of strings")
        normalized = code.strip()
        if not normalized:
            continue
        if normalized not in CALL_QUALITY_REASON_CODES:
            raise ValueError(f"Invalid call_quality_reason_code: {normalized}")
        if normalized not in normalized_codes:
            normalized_codes.append(normalized)
    return normalized_codes


async def extract_call_analytics(
    conversation_history: list[dict],
    transfer_purpose: str | None = None,
    close_reason: str | None = None,
    duration_seconds: float | None = None,
) -> dict:
    """
    Extract analytics from conversation using LLM.

    Args:
        conversation_history: List of message dicts in format [{"role": "user/assistant", "content": "..."}]
        transfer_purpose: Live routing purpose from call_transfer, if one was captured.
        close_reason: Voice provider close reason captured at end of call.
        duration_seconds: Call duration in seconds, if provided by the provider.

    Returns:
        dict: {
            "ended_reason": CallEndedReason,
            "call_purpose": list[CallPurpose],
            "user_satisfaction": UserSatisfaction,
            "language": CallLanguage,
            "transfer_reason_category": str | None,
            "transfer_agent_was_at_fault": bool | None,
            "call_quality_label": CallQualityLabel,
            "call_quality_reason_codes": list[str]
        }
    """
    import json

    from agent.model import ModelOptions, call_llm_default
    from db.tables.types import (
        CallEndedReason,
        CallLanguage,
        CallPurpose,
        CallQualityLabel,
        UserSatisfaction,
    )

    transfer_categories = ", ".join(TRANSFER_REASON_CATEGORIES)
    transfer_taxonomy = format_transfer_reason_taxonomy_for_prompt()
    transfer_fault_defaults = format_transfer_agent_fault_defaults_for_prompt()
    call_quality_taxonomy = format_call_quality_taxonomy_for_prompt()
    call_quality_reason_codes = ", ".join(CALL_QUALITY_REASON_CODES)
    transfer_purpose_context = transfer_purpose or "none"
    close_reason_context = close_reason or "unknown"
    duration_context = (
        f"{duration_seconds:.3f}" if duration_seconds is not None else "unknown"
    )

    # Build system prompt with all enum options
    system_prompt = f"""Analyze this restaurant phone-call conversation and extract one unified post-call analytics JSON object.

Use the transcript as the source of truth. Use the live transfer_purpose context only as a signal that the agent invoked call_transfer and how it tried to route the call.
Use the live close_reason and duration only as supporting context for ended_reason and call-quality reason codes. Do not duplicate misdialed or silence_timeout as call_quality_label values.

Global transfer signals:
- If live transfer_purpose is anything other than "none", treat the call as having a transfer signal.
- Empty speaker lines at the very end of the transcript usually mean the call was already bridged to a human / dead air on the bot side. Ignore them for intent analysis but treat them as a transfer signal.
- When a transfer signal exists, ended_reason should be assistant_forwarded unless the transcript clearly shows only a checkout/self-service handoff with no human transfer.

1. ended_reason: Choose ONE from:
   - customer_ended: Customer hung up or ended the call normally
   - assistant_forwarded: AI assistant transferred to human staff
   - misdialed: Wrong number or accidental call
   - silence_timeout: Call ended due to silence/no response
   - max_duration_exceeded: Call reached maximum allowed duration
   - other: Any other reason

2. call_purpose: Choose ALL caller intents that apply (can be multiple) from:
   - store_info: Hours, location/directions, parking, policies
   - menu_info: Menu questions (items, ingredients, pricing)
   - ordering: User wanted to place or modify an order, even if checkout failed or the call transferred
   - reservation: Making new reservations
   - waitlist: Waitlist inquiries
   - takeout_issue: Missing pickup items, wrong location
   - third_party_order: DoorDash/other app order updates
   - delivery: Delivery orders, availability, zones, fees, or issues
   - customer_service: Non-urgent management / general service
   - complaint_service: Dine-in or service complaints
   - complaint_food_safety: Food safety / food poisoning issues
   - dietary_specific: Allergy/dietary restriction beyond website info
   - lost_and_found: Lost items at the restaurant
   - reservation_change: Unsupported reservation changes
   - other: Any other call purpose

The call_purpose array must contain at least one of the exact values above. Do not invent adjacent labels such as catering or takeout order. For catering or large-party order requests, use call_purpose ["ordering"] and transfer_reason_category "capability_catering". For new reservation requests, use "reservation"; use "reservation_change" only for changing an existing reservation.

Do not use call_purpose for transfer root cause. Example: an order tool failure should usually have call_purpose ["ordering"] and transfer_reason_category "tool_failure_order".

3. call_quality_label: Choose ONE from:
{call_quality_taxonomy}

Quality classification rules:
   - Use legitimate_restaurant_call when there is a real restaurant/customer-service intent, even if the call later transfers, fails, or ends poorly.
   - Use promotional_sales for vendor/sales/marketing outreach even if the caller asks to speak to a manager.
   - Use robot_prerecorded when the caller side appears automated or prerecorded; use spam_scam when the content is suspicious/fraudulent.
   - Use prank_or_abusive when the caller is harassing, intentionally disruptive, or making a prank call with no legitimate restaurant purpose.
   - For calls that only indicate a wrong number/misdial or no substantive caller speech, use ended_reason (misdialed or silence_timeout) and set call_quality_label to unknown_unclear unless another quality label is supported.
   - Use unknown_unclear only when the transcript and provider context do not support another label.

4. call_quality_reason_codes: Choose zero or more exact reason codes from:
   {call_quality_reason_codes}

5. user_satisfaction: Choose ONE from:
   - positive: Customer satisfied, polite close, needs resolved
   - neutral: Mixed signals, partially resolved, or indifferent
   - negative: Dissatisfied, frustrated, or issue not resolved

6. language: Choose ONE from:
   - english: English conversation
   - french: French conversation
   - spanish: Spanish conversation
   - chinese: Chinese conversation

7. transfer_reason_category: Choose ONE from the transfer taxonomy below when the call had a human-transfer signal or transfer-like handoff wording, or null when there was no transfer signal.
   Valid categories: {transfer_categories}

   Transfer taxonomy decision rules, adapted from VSA:
{transfer_taxonomy}

   Transfer category precedence:
   1. If a transfer signal exists but the transcript only shows checkout, payment-link, reservation-link, or final-processing handoff with no human request or human connection, use checkout_handoff_not_human.
   2. If the first substantive caller utterance asks for a named/specific person or department, use capability_specific_person or capability_other_department, not cold_opt_out.
   3. If the first substantive caller utterance is a generic human request with no prior task intent, use cold_opt_out.
   4. If the caller stated an order/reservation/delivery/menu intent before asking for a human, do not use cold_opt_out. Classify the root cause from the later flow.
   5. If the caller only says hello, checks whether they are connected, gives an unclear request, or never gives a usable intent before the transfer signal, use ambiguous_intent_user_gave_up rather than other.

8. transfer_agent_was_at_fault: boolean or null.
{transfer_fault_defaults}

Return ONLY a valid JSON object with these exact keys: ended_reason, call_purpose, call_quality_label, call_quality_reason_codes, user_satisfaction, language, transfer_reason_category, transfer_agent_was_at_fault.
The call_purpose and call_quality_reason_codes values must be arrays of strings. ended_reason, call_quality_label, user_satisfaction, language, and transfer_reason_category must be strings or null as specified. transfer_agent_was_at_fault must be boolean or null.

Example format:
{{
  "ended_reason": "customer_ended",
  "call_purpose": ["menu_info", "ordering"],
  "call_quality_label": "legitimate_restaurant_call",
  "call_quality_reason_codes": ["restaurant_intent_present", "order_or_reservation_intent"],
  "user_satisfaction": "positive",
  "language": "english",
  "transfer_reason_category": null,
  "transfer_agent_was_at_fault": null
}}"""

    # Format conversation for LLM
    conversation_text = _format_conversation(conversation_history)

    logger.info("Starting LLM call analytics extraction")
    logger.debug(f"Conversation history length: {len(conversation_history)} messages")

    content: str | None = None
    result: dict | None = None

    try:
        # Call Azure OpenAI with JSON response format
        response = await call_llm_default(
            model_option=ModelOptions.GPT_4O,
            params={
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            "Live call_transfer purpose captured during the call: "
                            f"{transfer_purpose_context}\n"
                            f"Live close_reason captured at call end: {close_reason_context}\n"
                            f"Call duration seconds: {duration_context}\n\n"
                            f"Transcript:\n{conversation_text}"
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
        )

        # Parse JSON response
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty response")

        result = json.loads(content)
        logger.debug(f"LLM raw response: {result}")

        # Validate result is a dict
        if not isinstance(result, dict):
            raise ValueError("LLM response is not a valid JSON object")

        # Convert strings to enums
        analytics = {
            "ended_reason": CallEndedReason(result["ended_reason"]),
            "call_purpose": [CallPurpose(p) for p in result["call_purpose"]],
            "user_satisfaction": UserSatisfaction(result["user_satisfaction"]),
            "language": CallLanguage(result["language"]),
            "transfer_reason_category": _normalize_transfer_reason_category(
                result.get("transfer_reason_category")
            ),
            "transfer_agent_was_at_fault": _normalize_transfer_agent_was_at_fault(
                result.get("transfer_agent_was_at_fault")
            ),
            "call_quality_label": CallQualityLabel(result["call_quality_label"]),
            "call_quality_reason_codes": _normalize_call_quality_reason_codes(
                result["call_quality_reason_codes"]
            ),
        }

        # Log the extracted analytics
        logger.info("[Live Kit Analytics] Call analytics extraction successful")
        logger.info(
            f"[Live Kit Analytics]  Ended reason: {analytics['ended_reason'].value}"
        )
        logger.info(
            f"[Live Kit Analytics]  Call purposes: {[p.value for p in analytics['call_purpose']]}"
        )
        logger.info(
            f"[Live Kit Analytics]  User satisfaction: {analytics['user_satisfaction'].value}"
        )
        logger.info(f"[Live Kit Analytics]  Language: {analytics['language'].value}")
        logger.info(
            f"[Live Kit Analytics]  Transfer reason category: {analytics['transfer_reason_category']}"
        )
        logger.info(
            f"[Live Kit Analytics]  Transfer agent was at fault: {analytics['transfer_agent_was_at_fault']}"
        )
        logger.info(
            f"[Live Kit Analytics]  Call quality label: {analytics['call_quality_label'].value}"
        )
        logger.info(
            f"[Live Kit Analytics]  Call quality reason codes: {analytics['call_quality_reason_codes']}"
        )

        return analytics

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        if content:
            logger.error(f"Raw response content: {content}")
        raise
    except (KeyError, ValueError) as e:
        logger.error(f"Invalid LLM response format or enum value: {e}")
        if result:
            logger.error(f"Parsed result: {result}")
        raise
    except Exception:
        logger.exception("Unexpected error during call analytics extraction")
        raise
