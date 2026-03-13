"""
Slack Modal Builders

Builds Slack modal views for Mercury bot interactive workflows:
- Tool feedback submission
- Tool request submission
- Custom report generation
- Last X hours report
- Date range report
- Feedback client lookup
- Camera filter by account
- Subscription lookup
"""

from typing import Any, Dict

TIMEZONE_OPTIONS: list[Dict[str, Any]] = [
    {
        "text": {"type": "plain_text", "text": "Pacific (PT)"},
        "value": "America/Los_Angeles",
    },
    {
        "text": {"type": "plain_text", "text": "Mountain (MT)"},
        "value": "America/Denver",
    },
    {
        "text": {"type": "plain_text", "text": "Central (CT)"},
        "value": "America/Chicago",
    },
    {
        "text": {"type": "plain_text", "text": "Eastern (ET)"},
        "value": "America/New_York",
    },
    {
        "text": {"type": "plain_text", "text": "UTC"},
        "value": "UTC",
    },
]


def _build_account_options(
    accounts: list[tuple[str, str | None]],
) -> list[Dict[str, Any]]:
    """Build Slack static_select options from a list of (name, display_name) tuples."""
    options = []
    for name, display_name in accounts[:100]:
        label = f"{display_name} ({name})" if display_name else name
        options.append(
            {
                "text": {"type": "plain_text", "text": label[:75]},
                "value": name[:75],
            }
        )
    return options


def _build_account_select_block(
    accounts: list[tuple[str, str | None]],
    *,
    block_id: str = "account_name",
    action_id: str = "account_value",
    label: str = "Account Name (optional)",
    optional: bool = True,
    placeholder: str = "Select an account...",
) -> Dict[str, Any]:
    """Build an account select input block using a static_select dropdown."""
    options = _build_account_options(accounts)
    block: Dict[str, Any] = {
        "type": "input",
        "block_id": block_id,
        "optional": optional,
        "label": {"type": "plain_text", "text": label},
        "element": {
            "type": "static_select",
            "placeholder": {"type": "plain_text", "text": placeholder},
            "action_id": action_id,
        },
    }
    if options:
        block["element"]["options"] = options
    else:
        block["element"]["options"] = [
            {
                "text": {"type": "plain_text", "text": "No accounts found"},
                "value": "__none__",
            }
        ]
    return block


def _build_multi_account_select_block(
    accounts: list[tuple[str, str | None]],
    *,
    block_id: str = "account_names",
    action_id: str = "accounts_value",
    label: str = "Account Names (optional)",
    optional: bool = True,
    placeholder: str = "Select accounts...",
) -> Dict[str, Any]:
    """Build a multi-account select input block using multi_static_select."""
    options = _build_account_options(accounts)
    block: Dict[str, Any] = {
        "type": "input",
        "block_id": block_id,
        "optional": optional,
        "label": {"type": "plain_text", "text": label},
        "element": {
            "type": "multi_static_select",
            "placeholder": {"type": "plain_text", "text": placeholder},
            "action_id": action_id,
        },
    }
    if options:
        block["element"]["options"] = options
    else:
        block["element"]["options"] = [
            {
                "text": {"type": "plain_text", "text": "No accounts found"},
                "value": "__none__",
            }
        ]
    return block


def build_tool_feedback_modal(
    tools: list[dict], channel_id: str = ""
) -> Dict[str, Any]:
    """
    Build a Slack modal for submitting internal tool feedback.

    Args:
        tools: List of tool dicts with 'name', 'page_id', and 'owner_id' fields
        channel_id: Channel ID stored in private_metadata for response routing

    Returns:
        Dict: Slack view payload for views.open()
    """
    tool_options = [
        {
            "text": {"type": "plain_text", "text": tool["name"][:75]},
            "value": f"{tool['page_id']}|{tool.get('owner_id', '')}"[:75],
        }
        for tool in tools[:100]
    ]

    if not tool_options:
        return {
            "type": "modal",
            "callback_id": "mercury_tool_feedback_submit",
            "title": {"type": "plain_text", "text": "Tool Feedback"},
            "close": {"type": "plain_text", "text": "Close"},
            "private_metadata": channel_id,
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            ":information_source: *No internal tools found.*\n"
                            "There are no tools available for feedback at this time. "
                            "Please try again later or contact the tools team."
                        ),
                    },
                }
            ],
        }

    blocks: list[Dict[str, Any]] = [
        {
            "type": "input",
            "block_id": "tool_select",
            "label": {"type": "plain_text", "text": "Internal Tool"},
            "element": {
                "type": "static_select",
                "placeholder": {"type": "plain_text", "text": "Select a tool..."},
                "options": tool_options,
                "action_id": "tool_name",
            },
        },
        {
            "type": "input",
            "block_id": "feedback_type",
            "label": {"type": "plain_text", "text": "Request Type"},
            "element": {
                "type": "static_select",
                "placeholder": {"type": "plain_text", "text": "Select type..."},
                "options": [
                    {
                        "text": {"type": "plain_text", "text": "Bug"},
                        "value": "Bug",
                    },
                    {
                        "text": {"type": "plain_text", "text": "Improvement"},
                        "value": "Improvement",
                    },
                    {
                        "text": {"type": "plain_text", "text": "Feature request"},
                        "value": "Feature request",
                    },
                    {
                        "text": {"type": "plain_text", "text": "Usability"},
                        "value": "Usability",
                    },
                    {
                        "text": {"type": "plain_text", "text": "Access/permission"},
                        "value": "Access/permission",
                    },
                    {
                        "text": {"type": "plain_text", "text": "Question"},
                        "value": "Question",
                    },
                    {
                        "text": {"type": "plain_text", "text": "Other"},
                        "value": "Other",
                    },
                ],
                "action_id": "feedback_type_value",
            },
        },
        {
            "type": "input",
            "block_id": "priority",
            "label": {"type": "plain_text", "text": "Priority"},
            "element": {
                "type": "static_select",
                "placeholder": {"type": "plain_text", "text": "Select priority..."},
                "options": [
                    {
                        "text": {"type": "plain_text", "text": "P0 - Critical"},
                        "value": "P0",
                    },
                    {
                        "text": {"type": "plain_text", "text": "P1 - High"},
                        "value": "P1",
                    },
                    {
                        "text": {"type": "plain_text", "text": "P2 - Medium"},
                        "value": "P2",
                    },
                    {
                        "text": {"type": "plain_text", "text": "P3 - Low"},
                        "value": "P3",
                    },
                ],
                "action_id": "priority_value",
            },
        },
        {
            "type": "input",
            "block_id": "feedback_text",
            "label": {"type": "plain_text", "text": "Feedback"},
            "element": {
                "type": "plain_text_input",
                "multiline": True,
                "max_length": 2000,
                "placeholder": {
                    "type": "plain_text",
                    "text": "Describe the issue, suggestion, or question...",
                },
                "action_id": "feedback_content",
            },
        },
    ]

    return {
        "type": "modal",
        "callback_id": "mercury_tool_feedback_submit",
        "title": {"type": "plain_text", "text": "Tool Feedback"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": channel_id,
        "blocks": blocks,
    }


def build_tool_request_modal(channel_id: str = "") -> Dict[str, Any]:
    """
    Build a Slack modal for requesting a new internal tool.

    Args:
        channel_id: Channel ID stored in private_metadata for response routing

    Returns:
        Dict: Slack view payload for views.open()
    """
    return {
        "type": "modal",
        "callback_id": "mercury_tool_request_submit",
        "title": {"type": "plain_text", "text": "New Tool Request"},
        "submit": {"type": "plain_text", "text": "Submit"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": channel_id,
        "blocks": [
            {
                "type": "input",
                "block_id": "request_title",
                "label": {"type": "plain_text", "text": "Request"},
                "element": {
                    "type": "plain_text_input",
                    "max_length": 2000,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Short description of the tool...",
                    },
                    "action_id": "request_value",
                },
            },
            {
                "type": "input",
                "block_id": "priority",
                "label": {"type": "plain_text", "text": "Priority"},
                "element": {
                    "type": "static_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select priority...",
                    },
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": "P0 - Critical"},
                            "value": "P0",
                        },
                        {
                            "text": {"type": "plain_text", "text": "P1 - High"},
                            "value": "P1",
                        },
                        {
                            "text": {"type": "plain_text", "text": "P2 - Medium"},
                            "value": "P2",
                        },
                        {
                            "text": {"type": "plain_text", "text": "P3 - Low"},
                            "value": "P3",
                        },
                    ],
                    "action_id": "priority_value",
                },
            },
            {
                "type": "input",
                "block_id": "problem_context",
                "optional": True,
                "label": {"type": "plain_text", "text": "Problem / Context"},
                "element": {
                    "type": "plain_text_input",
                    "multiline": True,
                    "max_length": 2000,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Background and problem statement...",
                    },
                    "action_id": "problem_value",
                },
            },
            {
                "type": "input",
                "block_id": "proposed_solution",
                "optional": True,
                "label": {"type": "plain_text", "text": "Proposed Solution"},
                "element": {
                    "type": "plain_text_input",
                    "multiline": True,
                    "max_length": 2000,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Suggested approach or solution...",
                    },
                    "action_id": "solution_value",
                },
            },
        ],
    }


def build_report_modal(
    accounts: list[tuple[str, str | None]], channel_id: str = ""
) -> Dict[str, Any]:
    """
    Build a modal for generating a report with period and optional account filter.

    Args:
        accounts: List of (name, display_name) tuples for the dropdown
        channel_id: Channel ID for response routing

    Returns:
        Dict: Slack view payload
    """
    return {
        "type": "modal",
        "callback_id": "mercury_report_submit",
        "title": {"type": "plain_text", "text": "Generate Report"},
        "submit": {"type": "plain_text", "text": "Generate"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": channel_id,
        "blocks": [
            {
                "type": "input",
                "block_id": "report_period",
                "label": {"type": "plain_text", "text": "Report Period"},
                "element": {
                    "type": "static_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select period...",
                    },
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": "Daily"},
                            "value": "daily",
                        },
                        {
                            "text": {"type": "plain_text", "text": "Weekly"},
                            "value": "weekly",
                        },
                        {
                            "text": {"type": "plain_text", "text": "Monthly"},
                            "value": "monthly",
                        },
                    ],
                    "action_id": "period_value",
                },
            },
            _build_account_select_block(accounts),
        ],
    }


def build_feedback_lookup_modal(
    accounts: list[tuple[str, str | None]], channel_id: str = ""
) -> Dict[str, Any]:
    """
    Build a modal for looking up client feedback.

    Args:
        accounts: List of (name, display_name) tuples for the dropdown
        channel_id: Channel ID for response routing

    Returns:
        Dict: Slack view payload
    """
    return {
        "type": "modal",
        "callback_id": "mercury_feedback_lookup_submit",
        "title": {"type": "plain_text", "text": "Feedback Lookup"},
        "submit": {"type": "plain_text", "text": "Look Up"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": channel_id,
        "blocks": [
            _build_account_select_block(
                accounts,
                label="Account Name",
                optional=False,
                placeholder="Select an account...",
            ),
            {
                "type": "input",
                "block_id": "lookup_type",
                "label": {"type": "plain_text", "text": "Lookup Type"},
                "element": {
                    "type": "static_select",
                    "options": [
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Open Issues",
                            },
                            "value": "feedback",
                        },
                        {
                            "text": {
                                "type": "plain_text",
                                "text": "Full History",
                            },
                            "value": "feedback-status",
                        },
                    ],
                    "action_id": "lookup_value",
                },
            },
        ],
    }


def build_camera_filter_modal(
    accounts: list[tuple[str, str | None]], channel_id: str = ""
) -> Dict[str, Any]:
    """
    Build a modal for filtering camera status by account names.

    Args:
        accounts: List of (name, display_name) tuples for the multi-select dropdown
        channel_id: Channel ID for response routing

    Returns:
        Dict: Slack view payload
    """
    return {
        "type": "modal",
        "callback_id": "mercury_camera_filter_submit",
        "title": {"type": "plain_text", "text": "Camera Status"},
        "submit": {"type": "plain_text", "text": "Check"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": channel_id,
        "blocks": [
            _build_multi_account_select_block(accounts),
        ],
    }


def build_last_hours_modal(
    accounts: list[tuple[str, str | None]], channel_id: str = ""
) -> Dict[str, Any]:
    """
    Build a modal for generating a report for the last X hours.

    Args:
        accounts: List of (name, display_name) tuples for the dropdown
        channel_id: Channel ID for response routing

    Returns:
        Dict: Slack view payload
    """
    return {
        "type": "modal",
        "callback_id": "mercury_last_hours_submit",
        "title": {"type": "plain_text", "text": "Last X Hours Report"},
        "submit": {"type": "plain_text", "text": "Generate"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": channel_id,
        "blocks": [
            {
                "type": "input",
                "block_id": "hours",
                "label": {"type": "plain_text", "text": "Number of Hours"},
                "element": {
                    "type": "plain_text_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g. 6",
                    },
                    "action_id": "hours_value",
                },
            },
            _build_account_select_block(accounts),
        ],
    }


def build_date_range_modal(
    accounts: list[tuple[str, str | None]], channel_id: str = ""
) -> Dict[str, Any]:
    """
    Build a modal for generating a report over a custom date range
    with specific start/end times and timezone selection.

    Args:
        accounts: List of (name, display_name) tuples for the dropdown
        channel_id: Channel ID for response routing

    Returns:
        Dict: Slack view payload
    """
    return {
        "type": "modal",
        "callback_id": "mercury_date_range_submit",
        "title": {"type": "plain_text", "text": "Date Range Report"},
        "submit": {"type": "plain_text", "text": "Generate"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": channel_id,
        "blocks": [
            {
                "type": "input",
                "block_id": "start_date",
                "label": {"type": "plain_text", "text": "Start Date"},
                "element": {
                    "type": "datepicker",
                    "action_id": "start_date_value",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select start date...",
                    },
                },
            },
            {
                "type": "input",
                "block_id": "start_time",
                "optional": True,
                "label": {
                    "type": "plain_text",
                    "text": "Start Time",
                },
                "element": {
                    "type": "timepicker",
                    "action_id": "start_time_value",
                    "initial_time": "00:00",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select start time...",
                    },
                },
            },
            {
                "type": "input",
                "block_id": "end_date",
                "label": {"type": "plain_text", "text": "End Date"},
                "element": {
                    "type": "datepicker",
                    "action_id": "end_date_value",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select end date...",
                    },
                },
            },
            {
                "type": "input",
                "block_id": "end_time",
                "optional": True,
                "label": {
                    "type": "plain_text",
                    "text": "End Time",
                },
                "element": {
                    "type": "timepicker",
                    "action_id": "end_time_value",
                    "initial_time": "23:59",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select end time...",
                    },
                },
            },
            {
                "type": "input",
                "block_id": "timezone",
                "optional": True,
                "label": {
                    "type": "plain_text",
                    "text": "Timezone",
                },
                "element": {
                    "type": "static_select",
                    "action_id": "timezone_value",
                    "initial_option": TIMEZONE_OPTIONS[0],
                    "options": TIMEZONE_OPTIONS,
                },
            },
            _build_account_select_block(accounts),
        ],
    }


def build_subscription_lookup_modal(
    accounts: list[tuple[str, str | None]], channel_id: str = ""
) -> Dict[str, Any]:
    """
    Build a modal for looking up subscription status.

    Args:
        accounts: List of (name, display_name) tuples for the dropdown
        channel_id: Channel ID for response routing

    Returns:
        Dict: Slack view payload
    """
    return {
        "type": "modal",
        "callback_id": "mercury_subscription_submit",
        "title": {"type": "plain_text", "text": "Subscription Status"},
        "submit": {"type": "plain_text", "text": "Check"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": channel_id,
        "blocks": [
            _build_account_select_block(
                accounts,
                label="Account Name",
                optional=False,
                placeholder="Select an account...",
            ),
        ],
    }
