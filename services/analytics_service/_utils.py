from datetime import UTC, datetime, timedelta

from utils.log import logger

TRANSFER_REASON_CATEGORIES: tuple[str, ...] = (
    "cold_opt_out",
    "capability_specific_person",
    "user_frustration_in_flow",
    "capability_reservation",
    "tool_failure_order",
    "capability_catering",
    "other",
    "post_order_followup",
    "capability_other_department",
    "checkout_handoff_not_human",
    "ambiguous_intent_user_gave_up",
    "capability_hiring",
    "failed_transfer_attempt",
    "capability_off_topic",
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


async def extract_call_analytics(
    conversation_history: list[dict],
    transfer_purpose: str | None = None,
) -> dict:
    """
    Extract analytics from conversation using LLM.

    Args:
        conversation_history: List of message dicts in format [{"role": "user/assistant", "content": "..."}]
        transfer_purpose: Live routing purpose from call_transfer, if one was captured.

    Returns:
        dict: {
            "ended_reason": CallEndedReason,
            "call_purpose": list[CallPurpose],
            "user_satisfaction": UserSatisfaction,
            "language": CallLanguage,
            "transfer_reason_category": str | None,
            "transfer_agent_was_at_fault": bool | None
        }
    """
    import json

    from agent.model import ModelOptions, call_llm_default
    from db.tables.types import (
        CallEndedReason,
        CallLanguage,
        CallPurpose,
        UserSatisfaction,
    )

    transfer_categories = ", ".join(TRANSFER_REASON_CATEGORIES)
    transfer_purpose_context = transfer_purpose or "none"

    # Build system prompt with all enum options
    system_prompt = f"""Analyze this restaurant phone-call conversation and extract one unified post-call analytics JSON object.

Use the transcript as the source of truth. Use the live transfer_purpose context only as a signal that the agent invoked call_transfer and how it tried to route the call.

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

3. user_satisfaction: Choose ONE from:
   - positive: Customer satisfied, polite close, needs resolved
   - neutral: Mixed signals, partially resolved, or indifferent
   - negative: Dissatisfied, frustrated, or issue not resolved

4. language: Choose ONE from:
   - english: English conversation
   - french: French conversation
   - spanish: Spanish conversation
   - chinese: Chinese conversation

5. transfer_reason_category: Choose ONE from the transfer taxonomy below when the call had a human-transfer signal or transfer-like handoff wording, or null when there was no transfer signal.
   Valid categories: {transfer_categories}

   Transfer taxonomy decision rules, adapted from VSA:
   - cold_opt_out: The caller's first substantive utterance is a generic human request, such as "representative" or "speak to a person." Do not use this if the caller first stated another intent, or if the caller asked for a named/specific person or department.
   - capability_specific_person: Caller asks for a named employee, manager, front desk, or specific person.
   - capability_reservation: Agent says it cannot book or fully handle reservations and offers transfer.
   - capability_catering: Catering, large party, or event order the agent cannot fully handle.
   - capability_hiring: Job, hiring, or employment inquiry.
   - capability_other_department: Billing, corporate, supplier, accounts payable, or another non-restaurant department.
   - capability_off_topic: Wrong business or unrelated to restaurant operations.
   - tool_failure_order: Agent was placing/finalizing an order or checkout and a tool/order/payment/link-delivery error caused transfer. This includes cases where the caller did not receive an ordering or payment link.
   - user_frustration_in_flow: No explicit tool error, but repetition, missed details, or flow breakdown made the caller ask for a human.
   - post_order_followup: Order/payment link was already created, then caller asked for a human to confirm, modify, complain, or follow up.
   - ambiguous_intent_user_gave_up: Caller request was unclear, caller only greeted / checked connection, or agent asked for clarification and the call transferred before the caller gave a usable intent.
   - failed_transfer_attempt: Agent failed to connect, reported transfer could not happen, or initially refused to transfer before complying.
   - checkout_handoff_not_human: Transcript says the order/reservation was handed off for checkout, final processing, payment link, or self-service booking, but no human transfer actually occurred. Use this category instead of null when a transfer signal exists but the handoff was not to a human.
   - other: Use only when the transfer happened but none of the above fit.

   Transfer category precedence:
   1. If a transfer signal exists but the transcript only shows checkout, payment-link, reservation-link, or final-processing handoff with no human request or human connection, use checkout_handoff_not_human.
   2. If the first substantive caller utterance asks for a named/specific person or department, use capability_specific_person or capability_other_department, not cold_opt_out.
   3. If the first substantive caller utterance is a generic human request with no prior task intent, use cold_opt_out.
   4. If the caller stated an order/reservation/delivery/menu intent before asking for a human, do not use cold_opt_out. Classify the root cause from the later flow.
   5. If the caller only says hello, checks whether they are connected, gives an unclear request, or never gives a usable intent before the transfer signal, use ambiguous_intent_user_gave_up rather than other.

6. transfer_agent_was_at_fault: boolean or null.
   - true for agent/tool failures: tool_failure_order, user_frustration_in_flow, failed_transfer_attempt.
   - false for valid human handoff/product capability gaps: cold_opt_out, capability_* categories, post_order_followup, ambiguous_intent_user_gave_up.
   - false for checkout_handoff_not_human because it is a data-quality/routing-label issue, not caller-facing agent fault.
   - null when transfer_reason_category is null.

Return ONLY a valid JSON object with these exact keys: ended_reason, call_purpose, user_satisfaction, language, transfer_reason_category, transfer_agent_was_at_fault.
The call_purpose value must be an array of strings. ended_reason, user_satisfaction, language, and transfer_reason_category must be strings or null as specified. transfer_agent_was_at_fault must be boolean or null.

Example format:
{{
  "ended_reason": "customer_ended",
  "call_purpose": ["menu_info", "ordering"],
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
                            f"{transfer_purpose_context}\n\nTranscript:\n{conversation_text}"
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
